import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.handlers import admin_broadcast, chat_member, content, menu, more_features, referral, results_prices, start
from bot.middlewares.db_session import DbSessionMiddleware
from bot.middlewares.membership_gate import MembershipGateMiddleware
from bot.services.backup import run_daily_backup
from common.config import get_settings

try:
    import uvloop

    uvloop.install()  # faster event loop under high concurrency
except ImportError:
    pass

settings = get_settings()

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("bot.main")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware())
    dp.message.middleware(MembershipGateMiddleware())
    dp.callback_query.middleware(MembershipGateMiddleware())

    dp.include_router(start.router)
    dp.include_router(chat_member.router)
    dp.include_router(admin_broadcast.router)
    dp.include_router(menu.router)
    dp.include_router(referral.router)
    dp.include_router(more_features.router)
    dp.include_router(content.router)
    dp.include_router(results_prices.router)

    return dp


async def on_startup(bot: Bot):
    if settings.use_webhook:
        await bot.set_webhook(
            url=settings.webhook_url,
            secret_token=settings.webhook_secret or None,
            drop_pending_updates=False,
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"],
            max_connections=100,  # Telegram's max -- lets it push updates to us with more concurrency during bursts
        )
        logger.info("Webhook set to %s", settings.webhook_url)
    else:
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("Running in long-polling mode")

    scheduler = AsyncIOScheduler(timezone=settings.tz)
    scheduler.add_job(
        run_daily_backup,
        trigger=CronTrigger(hour=settings.backup_hour, minute=settings.backup_minute, timezone=settings.tz),
        args=[bot],
        id="daily_db_backup",
        misfire_grace_time=3600,  # still run if the process was briefly down at 08:00
    )
    scheduler.start()
    logger.info(
        "Daily backup scheduled for %02d:%02d %s, sending to chat_id=%s",
        settings.backup_hour, settings.backup_minute, settings.tz, settings.backup_admin_chat_id,
    )


async def on_shutdown(bot: Bot):
    await bot.session.close()


def main():
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.use_webhook:
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.webhook_secret or None,
        )
        webhook_requests_handler.register(app, path=f"{settings.webhook_path}/{settings.webhook_secret}")
        setup_application(app, dp, bot=bot)

        async def health(request):
            return web.Response(text="ok")

        app.router.add_get("/healthz", health)

        web.run_app(app, host=settings.webapp_host, port=settings.webapp_port)
    else:
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
