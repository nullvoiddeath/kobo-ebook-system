import logging
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

from kobo_automation.daily_content.poetry_fetcher import ContentItem

log = logging.getLogger(__name__)

_CSS = """
body { font-family: serif; line-height: 1.6; margin: 1em; }
.poem { white-space: pre-wrap; font-style: italic; }
p { text-indent: 1.5em; margin: 0.5em 0; }
h1 { text-align: center; margin-bottom: 1em; }
.author { text-align: center; font-style: italic; margin-bottom: 2em; }
"""

_COVER_WIDTH = 600
_COVER_HEIGHT = 900

_CONTENT_TYPE_LABELS = {
    "poem": "Daily Poem",
    "essay": "Daily Essay",
    "story": "Daily Story",
}


def _generate_cover(title: str, author: str, bg_color: str, text_color: str) -> bytes:
    img = Image.new("RGB", (_COVER_WIDTH, _COVER_HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)

    # Use default font (no external font files needed)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 36)
        author_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 24)
    except (OSError, IOError):
        title_font = ImageFont.load_default()
        author_font = ImageFont.load_default()

    # Word-wrap title
    max_chars = 25
    words = title.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    # Draw title centered
    y = _COVER_HEIGHT // 3
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        x = (_COVER_WIDTH - w) // 2
        draw.text((x, y), line, fill=text_color, font=title_font)
        y += 50

    # Draw author
    y += 30
    bbox = draw.textbbox((0, 0), author, font=author_font)
    w = bbox[2] - bbox[0]
    x = (_COVER_WIDTH - w) // 2
    draw.text((x, y), author, fill=text_color, font=author_font)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _format_body_html(item: ContentItem) -> str:
    if item.content_type == "poem":
        escaped = item.body.replace("&", "&amp;").replace("<", "&lt;")
        lines = escaped.split("\n")
        body = "<br/>\n".join(lines)
        return f'<div class="poem">{body}</div>'

    # Prose: split into paragraphs
    paragraphs = [p.strip() for p in item.body.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in item.body.split("\n") if p.strip()]
    html_parts = [f"<p>{p.replace(chr(10), ' ')}</p>" for p in paragraphs]
    return "\n".join(html_parts)


def build_epub(item: ContentItem, output_dir: str, config: dict) -> Path:
    today = date.today().isoformat()
    label = _CONTENT_TYPE_LABELS.get(item.content_type, "Daily Reading")
    full_title = f"{label}: {item.title}"

    book = epub.EpubBook()
    uid = str(uuid.uuid4())
    book.set_identifier(uid)
    book.set_title(full_title)
    book.set_language("en")
    book.add_author(item.author)
    book.add_metadata("DC", "date", today)
    book.add_metadata("DC", "subject", "daily-reading")

    # Cover
    epub_config = config.get("epub", {})
    bg = epub_config.get("cover_bg_color", "#2C3E50")
    fg = epub_config.get("cover_text_color", "#ECF0F1")
    cover_data = _generate_cover(item.title, item.author, bg, fg)
    book.set_cover("cover.jpg", cover_data)

    # Stylesheet
    style = epub.EpubItem(
        uid="style", file_name="style/default.css", media_type="text/css", content=_CSS.encode()
    )
    book.add_item(style)

    # Content chapter
    body_html = _format_body_html(item)
    chapter = epub.EpubHtml(title=item.title, file_name="content.xhtml", lang="en")
    chapter.content = f"""<html><body>
<h1>{item.title}</h1>
<p class="author">{item.author}</p>
{body_html}
</body></html>"""
    chapter.add_item(style)
    book.add_item(chapter)

    book.toc = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    # Write file
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in item.title)[:50]
    filename = f"{item.content_type}_{today}_{safe_title.strip()}.epub"
    out_path = Path(output_dir) / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(out_path), book)

    log.info("Created EPUB: %s", out_path)
    return out_path
