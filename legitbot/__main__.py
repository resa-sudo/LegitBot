"""Запуск из корня проекта: python -m legitbot."""

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.utils.token import TokenValidationError
from dotenv import load_dotenv

from .flow import create_router
from .photo_validation import get_provider


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
    )
    dispatcher.include_router(create_router())
    return dispatcher


async def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Не задан TELEGRAM_BOT_TOKEN. Скопируйте .env.example в .env "
            "и добавьте токен от @BotFather."
        )

    try:
        bot = Bot(token=token)
    except TokenValidationError:
        raise SystemExit(
            "Неверный формат TELEGRAM_BOT_TOKEN. Проверьте токен в .env."
        ) from None

    dispatcher = create_dispatcher()
    logging.getLogger(__name__).info("Photo validation provider: %s", get_provider())
    try:
        async with bot:
            # Проверяем токен перед ожиданием сообщений.
            await bot.get_me()
            logging.getLogger(__name__).info("Бот запущен. Остановка: Ctrl+C.")
            await dispatcher.start_polling(bot, close_bot_session=False)
    except TelegramUnauthorizedError:
        raise SystemExit(
            "Telegram отклонил токен. Проверьте TELEGRAM_BOT_TOKEN в .env."
        ) from None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
