import logging
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

from kobo_automation.utils.kepub_converter import convert_to_kepub
from kobo_automation.zlib_downloader.Zlibrary import Zlibrary
from kobo_automation.zlib_downloader.queue import (
    QueueEntry,
    mark_done,
    mark_failed,
    read_queue,
)

log = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\s\-]', '', name).strip()[:80]


def _score_result(book: dict, title: str, author: str) -> float:
    result_title = book.get("title", "")
    title_score = SequenceMatcher(None, title.lower(), result_title.lower()).ratio()

    if author:
        result_author = book.get("author", "")
        author_score = SequenceMatcher(None, author.lower(), result_author.lower()).ratio()
        return title_score * 0.6 + author_score * 0.4

    return title_score


def process_queue(config: dict) -> dict:
    paths = config.get("paths", {})
    zlib_cfg = config.get("zlib", {})
    queue_path = paths["queue_file"]
    ingest_dir = paths["ingest_dir"]
    delay = zlib_cfg.get("delay_between_downloads", 3)
    max_downloads = zlib_cfg.get("max_downloads_per_run", 5)
    extensions = zlib_cfg.get("preferred_extensions", ["epub"])
    kepubify_bin = config.get("kepubify", {}).get("binary", "kepubify")

    entries = read_queue(queue_path)
    if not entries:
        log.info("Queue is empty")
        return {"downloaded": 0, "failed": 0, "skipped": 0}

    # Auth: prefer remix tokens, fall back to email/password
    remix_userid = config.get("zlib_remix_userid", "")
    remix_userkey = config.get("zlib_remix_userkey", "")
    email = config.get("zlib_email", "")
    password = config.get("zlib_password", "")

    try:
        if remix_userid and remix_userkey:
            lib = Zlibrary(remix_userid=remix_userid, remix_userkey=remix_userkey)
        elif email and password:
            lib = Zlibrary(email=email, password=password)
        else:
            log.error("Z-Library credentials not configured in .env")
            for entry in entries:
                mark_failed(queue_path, entry, "no_credentials")
            return {"downloaded": 0, "failed": len(entries), "skipped": 0}

        if not lib.isLoggedIn():
            raise RuntimeError("Login returned success=false")
    except Exception as e:
        log.error("Z-Library login failed: %s", e)
        for entry in entries:
            mark_failed(queue_path, entry, "auth_error")
        return {"downloaded": 0, "failed": len(entries), "skipped": 0}

    stats = {"downloaded": 0, "failed": 0, "skipped": 0}

    for entry in entries[:max_downloads]:
        try:
            log.info("Searching for: %s", entry.title)
            results = lib.search(
                message=entry.title, extensions=extensions, limit=5
            )

            books = results.get("books", []) if results else []
            if not books:
                log.warning("No results for: %s", entry.title)
                mark_failed(queue_path, entry, "no_results")
                stats["failed"] += 1
                continue

            # Score and pick best match
            scored = [(b, _score_result(b, entry.title, entry.author)) for b in books]
            scored.sort(key=lambda x: x[1], reverse=True)
            best = scored[0][0]
            score = scored[0][1]

            if score < 0.3:
                log.warning("Best match score too low (%.2f) for: %s", score, entry.title)
                mark_failed(queue_path, entry, f"low_match_score_{score:.2f}")
                stats["failed"] += 1
                continue

            # Download book
            result = lib.downloadBook(best)
            if result is None:
                log.error("Download returned None for: %s", entry.title)
                mark_failed(queue_path, entry, "download_failed")
                stats["failed"] += 1
                continue

            filename, content = result
            # Use our sanitized name but keep the original extension
            ext = Path(filename).suffix if filename else ".epub"
            out_path = Path(ingest_dir) / f"{_sanitize_filename(entry.title)}{ext}"
            out_path.write_bytes(content)

            # Convert EPUB to KEPUB
            try:
                out_path = convert_to_kepub(out_path, kepubify_bin)
            except Exception as e:
                log.warning("KEPUB conversion failed for %s, keeping EPUB: %s", entry.title, e)

            log.info("Downloaded: %s -> %s", entry.title, out_path)
            mark_done(queue_path, entry)
            stats["downloaded"] += 1

        except Exception as e:
            log.exception("Failed to download: %s", entry.title)
            mark_failed(queue_path, entry, str(e)[:50])
            stats["failed"] += 1

        time.sleep(delay)

    remaining = len(entries) - max_downloads
    if remaining > 0:
        stats["skipped"] = remaining
        log.info("%d entries remaining in queue (will process next run)", remaining)

    return stats
