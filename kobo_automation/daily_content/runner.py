import asyncio
import logging

from kobo_automation.daily_content.epub_builder import build_epub
from kobo_automation.daily_content.gutenberg_fetcher import (
    fetch_random_essay,
    fetch_random_short_story,
)
from kobo_automation.daily_content.poetry_fetcher import fetch_random_poem
from kobo_automation.utils.kepub_converter import convert_to_kepub

log = logging.getLogger(__name__)


async def _fetch_poem():
    try:
        return await fetch_random_poem()
    except Exception:
        log.exception("Failed to fetch poem")
        return None


async def _fetch_essay(seen_ids_path: str, dedup_days: int):
    try:
        return await fetch_random_essay(seen_ids_path, dedup_days)
    except Exception:
        log.exception("Failed to fetch essay")
        return None


async def _fetch_story(seen_ids_path: str, dedup_days: int):
    try:
        return await fetch_random_short_story(seen_ids_path, dedup_days)
    except Exception:
        log.exception("Failed to fetch short story")
        return None


async def run_daily(config: dict) -> list[str]:
    daily_cfg = config.get("daily_content", {})
    paths = config.get("paths", {})
    ingest_dir = paths["ingest_dir"]
    seen_ids_path = paths["seen_ids_file"]
    dedup_days = daily_cfg.get("dedup_days", 90)
    kepubify_bin = config.get("kepubify", {}).get("binary", "kepubify")

    created = []

    if daily_cfg.get("poem", True):
        item = await _fetch_poem()
        if item:
            path = build_epub(item, ingest_dir, config)
            try:
                path = convert_to_kepub(path, kepubify_bin)
            except Exception as e:
                log.warning("KEPUB conversion failed for poem, keeping EPUB: %s", e)
            created.append(str(path))

    if daily_cfg.get("essay", True):
        item = await _fetch_essay(seen_ids_path, dedup_days)
        if item:
            path = build_epub(item, ingest_dir, config)
            try:
                path = convert_to_kepub(path, kepubify_bin)
            except Exception as e:
                log.warning("KEPUB conversion failed for essay, keeping EPUB: %s", e)
            created.append(str(path))

    if daily_cfg.get("short_story", True):
        item = await _fetch_story(seen_ids_path, dedup_days)
        if item:
            path = build_epub(item, ingest_dir, config)
            try:
                path = convert_to_kepub(path, kepubify_bin)
            except Exception as e:
                log.warning("KEPUB conversion failed for story, keeping EPUB: %s", e)
            created.append(str(path))

    log.info("Daily content: created %d/%d KEPUBs", len(created), 3)
    return created
