import asyncio
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

from zlibrary import AsyncZlib

from kobo_automation.zlib_downloader.queue import (
    QueueEntry,
    mark_done,
    mark_failed,
    read_queue,
)

log = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\s\-]', '', name).strip()[:80]


def _score_result(result, title: str, author: str) -> float:
    result_title = getattr(result, "name", "") or ""
    title_score = SequenceMatcher(None, title.lower(), result_title.lower()).ratio()

    if author:
        result_author = getattr(result, "author", "") or ""
        author_score = SequenceMatcher(None, author.lower(), result_author.lower()).ratio()
        return title_score * 0.6 + author_score * 0.4

    return title_score


async def process_queue(config: dict) -> dict:
    paths = config.get("paths", {})
    zlib_cfg = config.get("zlib", {})
    queue_path = paths["queue_file"]
    ingest_dir = paths["ingest_dir"]
    delay = zlib_cfg.get("delay_between_downloads", 3)
    max_downloads = zlib_cfg.get("max_downloads_per_run", 5)
    extensions = zlib_cfg.get("preferred_extensions", ["epub"])

    entries = read_queue(queue_path)
    if not entries:
        log.info("Queue is empty")
        return {"downloaded": 0, "failed": 0, "skipped": 0}

    email = config.get("zlib_email", "")
    password = config.get("zlib_password", "")
    if not email or not password:
        log.error("Z-Library credentials not configured in .env")
        for entry in entries:
            mark_failed(queue_path, entry, "no_credentials")
        return {"downloaded": 0, "failed": len(entries), "skipped": 0}

    lib = AsyncZlib()
    try:
        await lib.login(email, password)
    except Exception as e:
        log.error("Z-Library login failed: %s", e)
        for entry in entries:
            mark_failed(queue_path, entry, "auth_error")
        return {"downloaded": 0, "failed": len(entries), "skipped": 0}

    stats = {"downloaded": 0, "failed": 0, "skipped": 0}

    for entry in entries[:max_downloads]:
        try:
            log.info("Searching for: %s", entry.title)
            search_results = await lib.search(
                q=entry.title, extensions=extensions, count=5
            )

            results_list = []
            async for item in search_results:
                results_list.append(item)

            if not results_list:
                log.warning("No results for: %s", entry.title)
                mark_failed(queue_path, entry, "no_results")
                stats["failed"] += 1
                continue

            # Score and pick best match
            scored = [(r, _score_result(r, entry.title, entry.author)) for r in results_list]
            scored.sort(key=lambda x: x[1], reverse=True)
            best = scored[0][0]
            score = scored[0][1]

            if score < 0.3:
                log.warning("Best match score too low (%.2f) for: %s", score, entry.title)
                mark_failed(queue_path, entry, f"low_match_score_{score:.2f}")
                stats["failed"] += 1
                continue

            # Get book details and download
            book = await best.fetch()
            filename = f"{_sanitize_filename(entry.title)}.epub"
            filepath = Path(ingest_dir) / filename

            await book.download(str(filepath))
            log.info("Downloaded: %s -> %s", entry.title, filepath)
            mark_done(queue_path, entry)
            stats["downloaded"] += 1

        except Exception as e:
            log.exception("Failed to download: %s", entry.title)
            mark_failed(queue_path, entry, str(e)[:50])
            stats["failed"] += 1

        await asyncio.sleep(delay)

    remaining = len(entries) - max_downloads
    if remaining > 0:
        stats["skipped"] = remaining
        log.info("%d entries remaining in queue (will process next run)", remaining)

    return stats
