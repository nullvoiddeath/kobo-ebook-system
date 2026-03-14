# Kobo eBook System

Automated eBook management pipeline for Kobo eReaders. Runs on an Ubuntu server with [Calibre-Web Automated](https://github.com/crocodilestick/Calibre-Web-Automated) (CWA) handling library management, EPUB→KEPUB conversion, and Kobo sync.

## What It Does

**Daily Reading** — Every night, fetches and delivers to your Kobo:
- 1 random poem from [PoetryDB](https://poetrydb.org/) (~3,000 poems)
- 1 random essay from [Project Gutenberg](https://www.gutenberg.org/) (~4,600 essays)
- 1 random short story from [Project Gutenberg](https://www.gutenberg.org/) (~5,700 stories)

Each piece is formatted as an EPUB, pre-converted to KEPUB using [kepubify](https://pgaskin.net/kepubify/), and dropped into CWA for Kobo sync.

**Book Downloads** — Add books to a simple text queue, and they're automatically downloaded from Z-Library, converted to KEPUB, and synced to your Kobo.

## Architecture

```
┌──────────────────────┐     ┌──────────────────────────────┐
│  Python Automation   │     │  CWA Docker Container        │
│  (cron jobs)         │     │  (calibre-web-automated)     │
│                      │     │                              │
│  - daily content     │────▶│  /cwa-book-ingest/           │
│  - zlib downloader   │     │    → auto-import             │
│  - kepubify convert  │     │                              │
│                      │     │    → Kobo sync (:8083)       │
└──────────────────────┘     └──────────────────────────────┘
```

## Setup

### Prerequisites

- Ubuntu server (1GB RAM works, 2GB+ recommended)
- Docker and Docker Compose
- Python 3.11+
- [kepubify](https://pgaskin.net/kepubify/) — EPUB→KEPUB converter

### 1. Clone and configure

```bash
git clone git@github.com:nullvoiddeath/kobo-ebook-system.git
cd kobo-ebook-system

# Create .env with Z-Library credentials
cp .env.example .env
nano .env

# Edit config.yaml if needed (timezone, paths, etc.)
nano config.yaml
```

### 2. Install kepubify

```bash
# For ARM64 (OCI free tier Ampere)
curl -sL https://github.com/pgaskin/kepubify/releases/latest/download/kepubify-linux-arm64 \
  -o /usr/local/bin/kepubify && sudo chmod +x /usr/local/bin/kepubify

# For x86_64
# curl -sL https://github.com/pgaskin/kepubify/releases/latest/download/kepubify-linux-64bit \
#   -o /usr/local/bin/kepubify && sudo chmod +x /usr/local/bin/kepubify

kepubify --version  # verify installation
```

### 3. Install Python dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 4. Start CWA

```bash
docker compose up -d
```

CWA will be available at `http://<your-server>:8083`. Log in with default credentials (`admin` / `admin123`), change the password, then:

1. Go to **Admin → Edit Basic Configuration → Feature Configuration**
2. Enable **Kobo sync** and **Proxy unknown requests to Kobo Store**
3. Set target conversion format to **KEPUB**

### 5. Set up cron jobs

```bash
bash cron/setup_cron.sh
```

This installs:
- **2:00 AM daily** — fetch poem, essay, and short story
- **Every 6 hours** — process the book download queue

### 6. Connect your Kobo

1. Connect the Kobo to your computer via USB
2. Open `.kobo/Kobo eReader.conf`
3. Under `[OneStoreServices]`, set:
   ```
   api_endpoint=https://your-domain.com/kobo/<your-sync-token>
   ```
4. Eject and sync

### 7. (Recommended) Add swap for 1GB RAM servers

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Usage

```bash
# Fetch today's poem, essay, and short story
python -m kobo_automation daily

# Add a book to the download queue
python -m kobo_automation add "Dune" --author "Frank Herbert"

# Process the download queue
python -m kobo_automation download

# Check queue status
python -m kobo_automation status
```

## Book Queue

Edit `book_queue.txt` directly — one book per line:

```
# Format: title | author (optional)
Dune | Frank Herbert
Project Hail Mary
The Left Hand of Darkness | Ursula K. Le Guin
```

Processed entries are automatically marked:

```
DONE: Dune | Frank Herbert | 2026-03-14
FAILED: Nonexistent Book | no_results
```

## Configuration

**`config.yaml`** — non-secret settings (paths, daily content toggles, download limits, EPUB cover colors)

**`.env`** — Z-Library credentials (gitignored)

## Project Structure

```
kobo_automation/
├── __main__.py              # CLI entry point
├── config.py                # Config loader
├── daily_content/
│   ├── runner.py            # Daily fetch orchestrator
│   ├── poetry_fetcher.py    # PoetryDB API client
│   ├── gutenberg_fetcher.py # Gutendex API client
│   └── epub_builder.py      # EPUB creation (ebooklib + Pillow)
├── zlib_downloader/
│   ├── downloader.py        # Z-Library search & download
│   └── queue.py             # Queue file manager
└── utils/
    └── http_client.py       # Shared HTTP helpers
```
