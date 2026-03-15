import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from kobo_automation.config import load_config


def setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    log_dir = config["paths"]["log_dir"]
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        Path(log_dir) / "kobo_automation.log",
        maxBytes=log_cfg.get("max_file_size_mb", 10) * 1024 * 1024,
        backupCount=log_cfg.get("backup_count", 3),
    )
    console = logging.StreamHandler()

    level = getattr(logging, log_cfg.get("level", "INFO"))
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    handler.setFormatter(fmt)
    console.setFormatter(fmt)

    root = logging.getLogger("kobo_automation")
    root.setLevel(level)
    root.addHandler(handler)
    root.addHandler(console)


def cmd_daily(config: dict) -> None:
    from kobo_automation.daily_content.runner import run_daily

    created = asyncio.run(run_daily(config))
    print(f"Created {len(created)} EPUBs:")
    for path in created:
        print(f"  {path}")


def cmd_download(config: dict) -> None:
    from kobo_automation.zlib_downloader.downloader import process_queue

    stats = process_queue(config)
    print(f"Downloaded: {stats['downloaded']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}")


def cmd_add(config: dict, title: str, author: str) -> None:
    from kobo_automation.zlib_downloader.queue import add_to_queue

    add_to_queue(config["paths"]["queue_file"], title, author)
    print(f"Added: {title}" + (f" by {author}" if author else ""))


def cmd_status(config: dict) -> None:
    from kobo_automation.zlib_downloader.queue import read_queue

    queue_path = config["paths"]["queue_file"]
    entries = read_queue(queue_path)

    queue_file = Path(queue_path)
    if not queue_file.exists():
        print("No queue file found.")
        return

    lines = queue_file.read_text().splitlines()
    done = sum(1 for l in lines if l.startswith("DONE:"))
    failed = sum(1 for l in lines if l.startswith("FAILED:"))
    pending = len(entries)

    print(f"Queue: {pending} pending, {done} done, {failed} failed")
    if entries:
        print("\nPending:")
        for e in entries:
            author_str = f" by {e.author}" if e.author else ""
            print(f"  - {e.title}{author_str}")


def cmd_serve(config: dict) -> None:
    from kobo_automation.webapp import create_app

    webapp_cfg = config.get("webapp", {})
    host = webapp_cfg.get("host", "0.0.0.0")
    port = webapp_cfg.get("port", 8084)

    app = create_app(config)
    print(f"Starting book downloader at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kobo_automation", description="Kobo eBook automation")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("daily", help="Fetch daily poem, essay, and short story")
    sub.add_parser("download", help="Process the book download queue")

    add_parser = sub.add_parser("add", help="Add a book to the download queue")
    add_parser.add_argument("title", help="Book title")
    add_parser.add_argument("--author", default="", help="Book author")

    sub.add_parser("status", help="Show queue status")
    sub.add_parser("serve", help="Start the book download web interface")

    args = parser.parse_args()
    config = load_config()
    setup_logging(config)

    if args.command == "daily":
        cmd_daily(config)
    elif args.command == "download":
        cmd_download(config)
    elif args.command == "add":
        cmd_add(config, args.title, args.author)
    elif args.command == "status":
        cmd_status(config)
    elif args.command == "serve":
        cmd_serve(config)


if __name__ == "__main__":
    main()
