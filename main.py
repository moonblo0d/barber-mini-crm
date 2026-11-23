"""Точка входу: запускає веб-сервер і Telegram-бота в одному процесі."""
import asyncio
import logging

from aiohttp import web

import db
from config import BOT_TOKEN, WEB_HOST, WEB_PORT
from web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")


async def wait_for_telegram(bot) -> None:
    """Перевіряє токен; якщо Telegram просить зачекати (flood control) — чекає й пробує знову."""
    from aiogram.exceptions import TelegramRetryAfter

    while True:
        try:
            me = await bot.get_me()
            log.info("Бот підключений: @%s", me.username)
            return
        except TelegramRetryAfter as e:
            log.warning("Telegram просить зачекати %s с — чекаю…", e.retry_after)
            await asyncio.sleep(e.retry_after + 1)


async def setup_bot_profile(bot) -> None:
    """Меню команд бота (опис і аватар зручніше задати в @BotFather)."""
    from aiogram.types import BotCommand, BotCommandScopeChat

    from config import ADMIN_CHAT_ID

    try:
        await bot.set_my_commands([BotCommand(command="start", description="Записатися на стрижку")])
        if ADMIN_CHAT_ID:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Головне меню"),
                    BotCommand(command="leads", description="Останні заявки"),
                    BotCommand(command="stats", description="Статистика"),
                ],
                scope=BotCommandScopeChat(chat_id=ADMIN_CHAT_ID),
            )
    except Exception:
        log.exception("Не вдалося налаштувати профіль бота")


async def main() -> None:
    db.connect()

    bot = dp = None
    if BOT_TOKEN:
        from aiogram import Bot, Dispatcher
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.fsm.storage.memory import MemoryStorage

        from bot import router

        bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(router)
    else:
        log.warning("BOT_TOKEN не задано — працює лише сайт і панель (демо-режим)")

    runner = web.AppRunner(create_app(bot))
    await runner.setup()
    await web.TCPSite(runner, WEB_HOST, WEB_PORT).start()
    log.info("Сайт:   http://%s:%s/", WEB_HOST, WEB_PORT)
    log.info("Панель: http://%s:%s/admin  (логін admin)", WEB_HOST, WEB_PORT)

    try:
        if dp is not None:
            await wait_for_telegram(bot)
            await setup_bot_profile(bot)
            await dp.start_polling(bot)
        else:
            await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        if bot is not None:
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
