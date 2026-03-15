import logging
import threading

from flask import Flask, redirect, render_template_string, request, url_for

from kobo_automation.config import load_config
from kobo_automation.zlib_downloader.downloader import process_queue
from kobo_automation.zlib_downloader.queue import add_to_queue, read_queue

log = logging.getLogger(__name__)

PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Book Downloader</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: serif;
    font-size: 20px;
    line-height: 1.5;
    max-width: 700px;
    margin: 0 auto;
    padding: 20px;
    background: #fff;
    color: #000;
}
h1 { font-size: 28px; margin-bottom: 20px; border-bottom: 2px solid #000; padding-bottom: 10px; }
h2 { font-size: 22px; margin: 30px 0 10px; }
form { margin-bottom: 30px; }
label { display: block; font-weight: bold; margin-bottom: 6px; }
input[type="text"] {
    width: 100%;
    font-size: 20px;
    padding: 12px;
    border: 2px solid #000;
    margin-bottom: 16px;
    border-radius: 0;
    -webkit-appearance: none;
}
button {
    width: 100%;
    font-size: 22px;
    font-weight: bold;
    padding: 16px;
    background: #000;
    color: #fff;
    border: none;
    cursor: pointer;
    min-height: 56px;
}
.message {
    padding: 14px;
    border: 2px solid #000;
    margin-bottom: 20px;
    font-weight: bold;
}
.queue-item {
    padding: 10px 0;
    border-bottom: 1px solid #000;
    font-size: 18px;
}
.queue-item .status {
    font-weight: bold;
    font-size: 14px;
    text-transform: uppercase;
}
.status-done { }
.status-failed { text-decoration: underline; }
.status-pending { font-style: italic; }
.nav { margin-bottom: 20px; }
.nav a {
    font-size: 18px;
    color: #000;
    margin-right: 20px;
}
.empty { font-style: italic; color: #333; }
</style>
</head>
<body>
<h1>Book Downloader</h1>
<div class="nav">
    <a href="/">Add Book</a>
    <a href="/status">Queue Status</a>
</div>
{% block content %}{% endblock %}
</body>
</html>
"""

INDEX_TEMPLATE = (
    """{% extends "base" %}{% block content %}"""
    """{% if message %}<div class="message">{{ message }}</div>{% endif %}"""
    """<form method="POST" action="/add">"""
    """<label for="title">Book Title</label>"""
    """<input type="text" id="title" name="title" required placeholder="e.g. Dune">"""
    """<label for="author">Author (optional)</label>"""
    """<input type="text" id="author" name="author" placeholder="e.g. Frank Herbert">"""
    """<button type="submit">Download Book</button>"""
    """</form>"""
    """<h2>Recent Queue</h2>"""
    """{% if recent %}{% for item in recent %}"""
    """<div class="queue-item">"""
    """<span class="status status-{{ item.status }}">{{ item.status }}</span> """
    """{{ item.text }}</div>"""
    """{% endfor %}{% else %}<p class="empty">Queue is empty.</p>{% endif %}"""
    """{% endblock %}"""
)

STATUS_TEMPLATE = (
    """{% extends "base" %}{% block content %}"""
    """<h2>Pending ({{ counts.pending }})</h2>"""
    """{% if pending %}{% for e in pending %}"""
    """<div class="queue-item">{{ e.title }}{% if e.author %} — {{ e.author }}{% endif %}</div>"""
    """{% endfor %}{% else %}<p class="empty">No pending books.</p>{% endif %}"""
    """<h2>Completed ({{ counts.done }})</h2>"""
    """<h2>Failed ({{ counts.failed }})</h2>"""
    """{% endblock %}"""
)


def _parse_queue_lines(queue_path: str) -> list[dict]:
    """Parse all queue lines into status/text dicts for display."""
    from pathlib import Path

    path = Path(queue_path)
    if not path.exists():
        return []

    items = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("DONE:"):
            items.append({"status": "done", "text": line[5:].strip()})
        elif line.startswith("FAILED:"):
            items.append({"status": "failed", "text": line[7:].strip()})
        else:
            items.append({"status": "pending", "text": line})
    return items


def _count_queue(queue_path: str) -> dict:
    from pathlib import Path

    path = Path(queue_path)
    if not path.exists():
        return {"pending": 0, "done": 0, "failed": 0}

    lines = path.read_text().splitlines()
    done = sum(1 for l in lines if l.startswith("DONE:"))
    failed = sum(1 for l in lines if l.startswith("FAILED:"))
    pending = sum(
        1
        for l in lines
        if l.strip()
        and not l.startswith("#")
        and not l.startswith("DONE:")
        and not l.startswith("FAILED:")
    )
    return {"pending": pending, "done": done, "failed": failed}


def _download_in_background(config: dict) -> None:
    """Run process_queue in a background thread."""
    try:
        stats = process_queue(config)
        log.info(
            "Background download: %d downloaded, %d failed, %d skipped",
            stats["downloaded"],
            stats["failed"],
            stats["skipped"],
        )
    except Exception:
        log.exception("Background download failed")


def create_app(config: dict = None) -> Flask:
    if config is None:
        config = load_config()

    app = Flask(__name__)
    app.jinja_env.globals["base"] = PAGE_TEMPLATE
    app.jinja_loader = _InlineLoader(PAGE_TEMPLATE)

    queue_path = config["paths"]["queue_file"]

    @app.route("/")
    def index():
        message = request.args.get("message", "")
        recent = _parse_queue_lines(queue_path)[-10:]
        recent.reverse()
        return render_template_string(
            INDEX_TEMPLATE, message=message, recent=recent, base=PAGE_TEMPLATE
        )

    @app.route("/add", methods=["POST"])
    def add():
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()

        if not title:
            return redirect(url_for("index", message="Title is required."))

        add_to_queue(queue_path, title, author)

        # Kick off download in background
        thread = threading.Thread(
            target=_download_in_background, args=(config,), daemon=True
        )
        thread.start()

        desc = title + (f" by {author}" if author else "")
        return redirect(url_for("index", message=f"Queued: {desc}. Downloading..."))

    @app.route("/status")
    def status():
        pending = read_queue(queue_path)
        counts = _count_queue(queue_path)
        return render_template_string(
            STATUS_TEMPLATE, pending=pending, counts=counts, base=PAGE_TEMPLATE
        )

    return app


class _InlineLoader:
    """Custom Jinja loader that resolves 'base' to the inline page template."""

    def __init__(self, base_template: str):
        self._base = base_template

    def get_source(self, environment, template):
        if template == "base":
            return self._base, None, lambda: True
        raise Exception(f"Template not found: {template}")
