"""
Daily database backup. Runs pg_dump (custom format, restorable with
pg_restore), sends the resulting file straight to the admin's Telegram DM
(settings.backup_admin_chat_id) -- this is the actual durability guarantee:
a copy leaves the droplet every single day, so "server disappears" doesn't
mean "data disappears". A rolling 7-day local copy is also kept (mounted
volume, see docker-compose.yml) purely as a fast local restore option; it is
NOT the primary safety net, since it lives on the same droplet.

The admin account (backup_admin_chat_id) must have pressed /start on the bot
at least once -- Telegram only allows bots to message users who have
initiated contact. If that hasn't happened yet, sending silently fails and
this logs + tries to report the failure (which will also fail for the same
reason, but at least it's in the logs).
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from common.config import get_settings

settings = get_settings()
logger = logging.getLogger("bot.backup")

BACKUP_DIR = Path("/app/backups")
RETENTION_DAYS = 7


async def _run_pg_dump(out_path: Path) -> bool:
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.postgres_password

    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        "-h", settings.postgres_host,
        "-p", str(settings.postgres_port),
        "-U", settings.postgres_user,
        "-d", settings.postgres_db,
        "-Fc",  # custom format: compressed, restorable with pg_restore
        "-f", str(out_path),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("pg_dump failed (code %s): %s", proc.returncode, stderr.decode(errors="replace"))
        return False
    return True


def _prune_old_backups() -> None:
    if not BACKUP_DIR.exists():
        return
    files = sorted(BACKUP_DIR.glob("ielts_bot_*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[RETENTION_DAYS:]:
        try:
            old.unlink()
        except OSError:
            pass


async def run_daily_backup(bot: Bot) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = BACKUP_DIR / f"ielts_bot_{date_str}.dump"

    ok = await _run_pg_dump(out_path)
    if not ok:
        try:
            await bot.send_message(
                settings.backup_admin_chat_id,
                f"⚠️ {date_str}: kunlik DB backup MUVAFFAQIYATSIZ tugadi (pg_dump xatosi). Loglarni tekshiring.",
            )
        except Exception:
            logger.exception("Also failed to notify admin about the backup failure")
        return

    try:
        size_mb = out_path.stat().st_size / (1024 * 1024)
        await bot.send_document(
            settings.backup_admin_chat_id,
            FSInputFile(str(out_path), filename=out_path.name),
            caption=f"📦 Kunlik DB backup — {date_str} ({size_mb:.1f} MB)",
        )
        logger.info("Daily backup sent successfully: %s (%.1f MB)", out_path.name, size_mb)
    except Exception:
        logger.exception("Backup file created but failed to send via Telegram")
    finally:
        _prune_old_backups()
