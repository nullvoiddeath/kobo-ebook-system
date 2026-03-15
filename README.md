# Kobo eBook System

Automated eBook management pipeline for Kobo eReaders. Runs on an Ubuntu server (tested on OCI free tier, 1GB RAM) with [Calibre-Web Automated](https://github.com/crocodilestick/Calibre-Web-Automated) (CWA) handling library management, EPUB-to-KEPUB conversion, and Kobo sync.

## What It Does

**Book Downloads** — Queue books via a web UI (works on Kobo's built-in browser) or CLI. Books are automatically downloaded from Z-Library, ingested into CWA, converted to KEPUB, and synced to your Kobo.

**Daily Reading** — A cron job fetches and delivers to your Kobo:
- 1 random poem from [PoetryDB](https://poetrydb.org/) (~3,000 poems)
- 1 random essay from [Project Gutenberg](https://www.gutenberg.org/) (~4,600 essays)
- 1 random short story from [Project Gutenberg](https://www.gutenberg.org/) (~5,700 stories)

Each piece is formatted as an EPUB with a generated cover, dropped into CWA for automatic KEPUB conversion and Kobo sync.

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │            Ubuntu Server (OCI)          │
                    │                                         │
┌──────────┐       │  ┌───────────┐     ┌─────────────────┐  │
│  Kobo    │       │  │  Flask    │     │  CWA Docker     │  │
│  Clara   │◄──────┼──┤  Webapp   │────▶│  Container      │  │
│  BW      │  sync │  │  (:8084)  │     │  (:8083)        │  │
│          │───────┼─▶│           │     │                 │  │
│ (browser)│ queue │  ├───────────┤     │ - auto-import   │  │
└──────────┘       │  │  Cron     │────▶│ - EPUB → KEPUB  │  │
                    │  │  Jobs     │     │ - Kobo sync     │  │
                    │  └───────────┘     └─────────────────┘  │
                    │                                         │
                    │  Nginx reverse proxy + Cloudflare SSL   │
                    └─────────────────────────────────────────┘
```

## Prerequisites

- Ubuntu server (1GB RAM minimum — OCI always-free Ampere works)
- Docker and Docker Compose
- Python 3.11+
- A domain managed by Cloudflare (for HTTPS + DNS)

## Setup

### 1. Clone and configure

```bash
git clone git@github.com:nullvoiddeath/kobo-ebook-system.git
cd kobo-ebook-system

cp .env.example .env
nano .env
```

Set your Z-Library credentials and webapp auth in `.env`:

```env
ZLIB_EMAIL=your_email@example.com
ZLIB_PASSWORD=your_password

# Optional: remix tokens (more reliable than email/password)
# ZLIB_REMIX_USERID=your_user_id
# ZLIB_REMIX_USERKEY=your_user_key

WEBAPP_USERNAME=admin
WEBAPP_PASSWORD=your_secure_password
```

Edit `config.yaml` if needed (timezone, paths, download limits, etc.).

### 2. Install Python dependencies

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Add swap (required for 1GB RAM servers)

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swakon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 4. Start CWA

```bash
docker compose up -d
```

CWA will be available at `http://<your-server>:8083`. Log in with default credentials (`admin` / `admin123`), change the password, then:

1. Go to **Admin → Edit Basic Configuration → Feature Configuration**
2. Enable **Kobo sync** and **Proxy unknown requests to Kobo Store**
3. Set target conversion format to **KEPUB**

### 5. Fix ingest folder permissions

CWA's Docker volume may create the ingest folder as root. The Python automation needs write access:

```bash
sudo chown -R ubuntu:ubuntu ~/kobo-ebook-system/cwa-book-ingest
chmod 1777 ~/kobo-ebook-system/cwa-book-ingest
```

### 6. Set up Nginx reverse proxy

Install Nginx:

```bash
sudo apt install nginx
```

Generate a Cloudflare origin certificate (Dashboard → SSL/TLS → Origin Server → Create Certificate) and save it:

```bash
sudo mkdir -p /etc/ssl/cloudflare
# Save certificate to /etc/ssl/cloudflare/yourdomain.com.pem
# Save private key to /etc/ssl/cloudflare/yourdomain.com.key
```

Create `/etc/nginx/sites-available/kobo`:

```nginx
server {
    listen 443 ssl;
    server_name books.yourdomain.com;

    ssl_certificate     /etc/ssl/cloudflare/yourdomain.com.pem;
    ssl_certificate_key /etc/ssl/cloudflare/yourdomain.com.key;

    location / {
        proxy_pass http://127.0.0.1:8084;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl;
    server_name calibre.yourdomain.com;

    ssl_certificate     /etc/ssl/cloudflare/yourdomain.com.pem;
    ssl_certificate_key /etc/ssl/cloudflare/yourdomain.com.key;

    client_max_body_size 200M;

    # CWA Kobo sync sends large headers
    proxy_buffer_size       128k;
    proxy_buffers           4 256k;
    proxy_busy_buffers_size 256k;

    proxy_read_timeout  300;
    proxy_connect_timeout 60;
    proxy_send_timeout  300;

    location / {
        proxy_pass http://127.0.0.1:8083;
        proxy_set_header Host              calibre.yourdomain.com;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host  calibre.yourdomain.com;
        proxy_set_header X-Script-Name     "";
    }
}
```

Enable and start:

```bash
sudo ln -s /etc/nginx/sites-available/kobo /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
```

### 7. Configure Cloudflare DNS

Add two A records pointing to your server's public IP (orange cloud enabled):
- `books` → `<OCI_PUBLIC_IP>`
- `calibre` → `<OCI_PUBLIC_IP>`

Set SSL/TLS mode to **Full (Strict)**.

### 8. Open firewall ports

**iptables** — insert rules *before* the REJECT rule (check position with `sudo iptables --list --line-numbers`):

```bash
sudo iptables -I INPUT 5 -p tcp --dport 443 -m state --state NEW -j ACCEPT
sudo iptables -I INPUT 6 -p tcp --dport 8084 -m state --state NEW -j ACCEPT
sudo netfilter-persistent save
```

**OCI Security List** — add ingress rules for TCP ports 443 and 8084 with source `0.0.0.0/0`.

### 9. Set up the webapp as a systemd service

```bash
sudo tee /etc/systemd/system/kobo-webapp.service > /dev/null <<EOF
[Unit]
Description=Kobo Book Downloader Web UI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/kobo-ebook-system
ExecStart=/home/ubuntu/kobo-ebook-system/.venv/bin/python -m kobo_automation serve
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now kobo-webapp
```

### 10. Set up cron jobs

```bash
# Daily content every 3 days at 2:00 AM
(crontab -l 2>/dev/null; echo '0 2 */3 * * cd /home/ubuntu/kobo-ebook-system && /home/ubuntu/kobo-ebook-system/.venv/bin/python -m kobo_automation daily >> /home/ubuntu/kobo-ebook-system/logs/daily_cron.log 2>&1') | crontab -
```

### 11. Connect your Kobo

1. Connect the Kobo to your computer via USB
2. Open `.kobo/Kobo eReader.conf`
3. Under `[OneStoreServices]`, set:
   ```
   api_endpoint=https://calibre.yourdomain.com/kobo/<your-sync-token>
   ```
   (Get the sync token from CWA's admin panel under your user profile)
4. Eject and sync

## Usage

### Web Interface

Open `https://books.yourdomain.com` on your Kobo's browser or any device. Log in with your webapp credentials, enter a book title and optional author, and tap **Download Book**.

### CLI

```bash
# Fetch a poem, essay, and short story
python -m kobo_automation daily

# Add a book to the download queue
python -m kobo_automation add "Dune" --author "Frank Herbert"

# Process the download queue
python -m kobo_automation download

# Check queue status
python -m kobo_automation status

# Start the web server manually
python -m kobo_automation serve
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

**`config.yaml`** — non-secret settings:

| Section | Key settings |
|---------|-------------|
| `paths` | ingest dir, log dir, queue file, seen IDs file |
| `daily_content` | enable/disable poem/essay/story, max word count, dedup days |
| `zlib` | download delay, max per run, preferred file extensions |
| `epub` | cover background/text colors |
| `webapp` | host, port |
| `logging` | level, max file size, backup count |

**`.env`** — secrets (gitignored): Z-Library credentials, webapp auth, optional remix tokens.

## Project Structure

```
kobo-ebook-system/
├── docker-compose.yml           # CWA container config
├── config.yaml                  # Non-secret settings
├── .env                         # Secrets (gitignored)
├── .env.example                 # Template for .env
├── requirements.txt             # Python dependencies
├── book_queue.txt               # User-editable download queue
├── cwa-config/                  # CWA config volume (gitignored)
├── calibre-library/             # CWA library volume (gitignored)
├── cwa-book-ingest/             # Shared ingest folder (gitignored)
├── data/
│   └── seen_gutenberg_ids.json  # Daily content dedup tracker
├── logs/                        # Log files (gitignored)
├── cron/
│   └── setup_cron.sh
└── kobo_automation/
    ├── __init__.py
    ├── __main__.py              # CLI entry point
    ├── webapp.py                # Flask web UI (auth + queue + status)
    ├── config.py                # Config + env loader
    ├── daily_content/
    │   ├── runner.py            # Daily fetch orchestrator
    │   ├── poetry_fetcher.py    # PoetryDB API client
    │   ├── gutenberg_fetcher.py # Gutendex API client
    │   └── epub_builder.py      # EPUB creation (ebooklib + Pillow)
    ├── zlib_downloader/
    │   ├── Zlibrary.py          # Vendored Z-Library API client
    │   ├── downloader.py        # Search, score, download books
    │   └── queue.py             # Queue file parser/manager
    └── utils/
        └── http_client.py       # Shared HTTP helpers
```

## Troubleshooting

**Kobo sync fails with "upstream sent too big header"**
Add larger proxy buffers to the Nginx config for the CWA server block (see step 6).

**Kobo downloads show `localhost` URLs**
Set `X-Forwarded-Host` and `Host` headers in Nginx to your public domain (see step 6).

**Permission denied writing to `cwa-book-ingest/`**
Docker may have created the directory as root. Fix with:
```bash
sudo chown -R ubuntu:ubuntu ~/kobo-ebook-system/cwa-book-ingest
chmod 1777 ~/kobo-ebook-system/cwa-book-ingest
```

**Z-Library `ParseError: Could not parse book list`**
The old `zlibrary` PyPI package scrapes HTML which breaks when Z-Library changes their site. This project uses the [bipinkrish/Zlibrary-API](https://github.com/bipinkrish/Zlibrary-API) which uses Z-Library's internal API instead.

**Z-Library `IncompleteRead` errors**
Common on cloud VMs with flaky connections. The downloader has built-in retry logic (3 attempts with streaming).

**Port not accessible from outside**
On OCI, check *both* iptables and the VCN Security List. iptables rules must be inserted *before* the default REJECT rule — rules added after it are never reached.

**Webapp session expires immediately**
Sessions are configured with `session.permanent = True` and a 30-day lifetime. Ensure cookies are not being blocked by your browser.
