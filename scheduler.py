import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from telegram.error import Forbidden, TelegramError

from config import DAILY_HOUR, DAILY_MINUTE
from database import (
    get_all_subscribed,
    increment_day,
    unsubscribe,
    is_subscription_active,
    has_lesson_sent_today,
)
from messages import format_daily_message, FREE_LESSONS_COUNT

logger = logging.getLogger(__name__)


async def send_evening_checkin(bot: Bot):
    users = get_all_subscribed()
    sent = 0
    logger.info("Вечерний чек-ин: %d подписчиков в очереди", len(users))

    for user in users:
        user_id = user["user_id"]
        if not has_lesson_sent_today(user_id):
            continue

        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "Добрый вечер! 🌇\n\n"
                    "Как прошло сегодняшнее задание?\n\n"
                    "Нажмите «✅ Выполнено» — зафиксируйте результат, пока свежо в памяти."
                ),
            )
            sent += 1
        except Forbidden:
            unsubscribe(user_id)
        except TelegramError as e:
            logger.error("Ошибка чек-ина %d: %s", user_id, e)

    logger.info("Вечерний чек-ин завершён: отправлено %d", sent)


async def send_daily_messages(bot: Bot):
    users = get_all_subscribed()
    sent = skipped = 0
    logger.info("Рассылка запущена: %d подписчиков в очереди", len(users))

    for user in users:
        user_id = user["user_id"]

        # Баг #4 исправлен: идемпотентность — не отправлять дважды в один день
        if has_lesson_sent_today(user_id):
            skipped += 1
            continue

        # Баг #1 исправлен: проверяем доступ перед отправкой
        day_index = user["day_index"]
        has_free = day_index < FREE_LESSONS_COUNT
        has_sub = is_subscription_active(user_id)

        if not has_free and not has_sub:
            skipped += 1
            continue

        try:
            text = format_daily_message(user["first_name"], day_index)
            await bot.send_message(chat_id=user_id, text=text)
            increment_day(user_id)
            sent += 1
        except Forbidden:
            unsubscribe(user_id)
            logger.info("Пользователь %d заблокировал бота — отписан", user_id)
        except TelegramError as e:
            logger.error("Ошибка отправки %d: %s", user_id, e)

    logger.info("Рассылка завершена: отправлено %d, пропущено %d", sent, skipped)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_messages,
        trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE, timezone="Europe/Moscow"),
        args=[bot],
        id="daily_messages",
        replace_existing=True,
    )
    scheduler.add_job(
        send_evening_checkin,
        trigger=CronTrigger(hour=18, minute=0, timezone="Europe/Moscow"),
        args=[bot],
        id="evening_checkin",
        replace_existing=True,
    )
    return scheduler
