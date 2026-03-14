import asyncio
import logging
from dataclasses import dataclass

from kobo_automation.utils.http_client import fetch_json

log = logging.getLogger(__name__)

POETRYDB_RANDOM_URL = "https://poetrydb.org/random/1"


@dataclass
class ContentItem:
    title: str
    author: str
    body: str
    content_type: str  # "poem", "essay", "story"


async def fetch_random_poem() -> ContentItem:
    data = await fetch_json(POETRYDB_RANDOM_URL)
    poem = data[0]
    title = poem["title"]
    author = poem["author"]
    lines = poem["lines"]
    body = "\n".join(lines)
    log.info("Fetched poem: '%s' by %s (%d lines)", title, author, len(lines))
    return ContentItem(title=title, author=author, body=body, content_type="poem")
