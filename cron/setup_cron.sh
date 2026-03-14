#!/bin/bash
# Install cron jobs for kobo-ebook-system
# Run this once on the OCI VM after deployment

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PROJECT_DIR}/.venv/bin/python"

# Daily content at 2:00 AM
DAILY_CRON="0 2 * * * cd ${PROJECT_DIR} && ${PYTHON} -m kobo_automation daily >> ${PROJECT_DIR}/logs/daily_cron.log 2>&1"

# Queue processor every 6 hours
DOWNLOAD_CRON="0 */6 * * * cd ${PROJECT_DIR} && ${PYTHON} -m kobo_automation download >> ${PROJECT_DIR}/logs/download_cron.log 2>&1"

# Add to crontab (preserving existing entries)
(crontab -l 2>/dev/null | grep -v "kobo_automation"; echo "$DAILY_CRON"; echo "$DOWNLOAD_CRON") | crontab -

echo "Cron jobs installed:"
echo "  - Daily content fetch at 2:00 AM"
echo "  - Queue processor every 6 hours"
echo ""
crontab -l | grep kobo_automation
