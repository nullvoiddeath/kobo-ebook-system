import json
import logging
import random
import re
from datetime import date, timedelta
from pathlib import Path

from kobo_automation.daily_content.poetry_fetcher import ContentItem
from kobo_automation.utils.http_client import fetch_json, fetch_text

log = logging.getLogger(__name__)

GUTENDEX_URL = "https://gutendex.com/books"
PAGE_SIZE = 32
MAX_WORD_COUNT = 10000
MIN_SEGMENT_WORDS = 500
MAX_RETRIES = 3

# Patterns for splitting collections into individual works
_CHAPTER_PATTERNS = [
    re.compile(r"^\s{0,4}(?:CHAPTER|Chapter)\s+", re.MULTILINE),
    re.compile(r"^\s{0,4}[IVXLC]+\.?\s*$", re.MULTILINE),
    re.compile(r"^[A-Z][A-Z\s]{5,}$", re.MULTILINE),
]

_BOILERPLATE_START = re.compile(
    r"\*{3}\s*START OF (?:THE |THIS )?PROJECT GUTENBERG", re.IGNORECASE
)
_BOILERPLATE_END = re.compile(
    r"\*{3}\s*END OF (?:THE |THIS )?PROJECT GUTENBERG", re.IGNORECASE
)


def _load_seen_ids(path: str) -> dict[int, str]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        return {int(k): v for k, v in json.load(f).items()}


def _save_seen_ids(path: str, seen: dict[int, str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(seen, f)
    tmp.rename(p)


def _strip_boilerplate(text: str) -> str:
    start = _BOILERPLATE_START.search(text)
    if start:
        # Skip past the marker line
        newline = text.find("\n", start.end())
        text = text[newline + 1 :] if newline != -1 else text[start.end() :]

    end = _BOILERPLATE_END.search(text)
    if end:
        text = text[: end.start()]

    return text.strip()


def _split_into_segments(text: str) -> list[str]:
    # Try splitting on triple+ newlines first
    segments = re.split(r"\n{3,}", text)
    if len(segments) >= 3:
        return [s.strip() for s in segments if s.strip()]

    # Try chapter/heading patterns
    for pattern in _CHAPTER_PATTERNS:
        parts = pattern.split(text)
        if len(parts) >= 3:
            return [s.strip() for s in parts if s.strip()]

    return [text]


def _pick_segment(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text

    segments = _split_into_segments(text)
    suitable = [
        s for s in segments if MIN_SEGMENT_WORDS <= len(s.split()) <= max_words
    ]

    if suitable:
        return random.choice(suitable)

    # Fallback: take first max_words words
    return " ".join(words[:max_words])


def _get_text_url(book: dict) -> str | None:
    formats = book.get("formats", {})
    for key in formats:
        if "text/plain" in key:
            return formats[key]
    return None


async def _fetch_random_gutenberg(
    topic: str,
    content_type: str,
    seen_ids_path: str,
    dedup_days: int,
    max_words: int,
) -> ContentItem:
    seen = _load_seen_ids(seen_ids_path)
    cutoff = (date.today() - timedelta(days=dedup_days)).isoformat()
    # Remove expired entries
    seen = {k: v for k, v in seen.items() if v > cutoff}

    # Get total count
    data = await fetch_json(GUTENDEX_URL, {"topic": topic, "languages": "en"})
    total = data.get("count", 0)
    if total == 0:
        raise ValueError(f"No Gutenberg results for topic={topic}")

    max_page = max(1, total // PAGE_SIZE)

    for attempt in range(MAX_RETRIES):
        page = random.randint(1, max_page)
        page_data = await fetch_json(
            GUTENDEX_URL, {"topic": topic, "languages": "en", "page": page}
        )
        results = page_data.get("results", [])
        if not results:
            continue

        random.shuffle(results)
        for book in results:
            book_id = book["id"]
            if book_id in seen:
                continue

            text_url = _get_text_url(book)
            if not text_url:
                continue

            authors = book.get("authors", [])
            author = authors[0]["name"] if authors else "Unknown"
            title = book.get("title", "Untitled")

            try:
                raw_text = await fetch_text(text_url)
            except Exception:
                log.warning("Failed to download text for %s (id=%d)", title, book_id)
                continue

            cleaned = _strip_boilerplate(raw_text)
            if len(cleaned.split()) < MIN_SEGMENT_WORDS:
                continue

            body = _pick_segment(cleaned, max_words)

            seen[book_id] = date.today().isoformat()
            _save_seen_ids(seen_ids_path, seen)

            log.info(
                "Fetched %s: '%s' by %s (%d words)",
                content_type,
                title,
                author,
                len(body.split()),
            )
            return ContentItem(
                title=title, author=author, body=body, content_type=content_type
            )

    raise RuntimeError(
        f"Could not find suitable {content_type} after {MAX_RETRIES} attempts"
    )


async def fetch_random_essay(seen_ids_path: str, dedup_days: int = 90) -> ContentItem:
    return await _fetch_random_gutenberg(
        topic="essays",
        content_type="essay",
        seen_ids_path=seen_ids_path,
        dedup_days=dedup_days,
        max_words=MAX_WORD_COUNT,
    )


async def fetch_random_short_story(
    seen_ids_path: str, dedup_days: int = 90
) -> ContentItem:
    return await _fetch_random_gutenberg(
        topic="short stories",
        content_type="story",
        seen_ids_path=seen_ids_path,
        dedup_days=dedup_days,
        max_words=MAX_WORD_COUNT,
    )
