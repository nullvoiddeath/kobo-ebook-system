import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class QueueEntry:
    title: str
    author: str
    line_number: int
    raw_line: str


def read_queue(queue_path: str) -> list[QueueEntry]:
    path = Path(queue_path)
    if not path.exists():
        return []

    entries = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("DONE:") or line.startswith("FAILED:"):
                continue

            parts = [p.strip() for p in line.split("|")]
            title = parts[0]
            author = parts[1] if len(parts) > 1 else ""
            entries.append(QueueEntry(title=title, author=author, line_number=i, raw_line=line))

    return entries


def mark_done(queue_path: str, entry: QueueEntry) -> None:
    _update_line(queue_path, entry, f"DONE: {entry.raw_line} | {date.today().isoformat()}")


def mark_failed(queue_path: str, entry: QueueEntry, reason: str) -> None:
    _update_line(queue_path, entry, f"FAILED: {entry.raw_line} | {reason}")


def _update_line(queue_path: str, entry: QueueEntry, new_line: str) -> None:
    path = Path(queue_path)
    lines = path.read_text().splitlines(keepends=True)
    idx = entry.line_number - 1
    if idx < len(lines):
        lines[idx] = new_line + "\n"
    path.write_text("".join(lines))


def add_to_queue(queue_path: str, title: str, author: str = "") -> None:
    path = Path(queue_path)
    line = title
    if author:
        line = f"{title} | {author}"
    with open(path, "a") as f:
        f.write(line + "\n")
    log.info("Added to queue: %s", line)
