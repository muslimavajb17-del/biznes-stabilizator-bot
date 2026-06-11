import asyncio
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    PAYMENT_PROVIDER_TOKEN,
    SUBSCRIPTION_PRICE_KOPECKS,
    SUBSCRIPTION_DAYS,
)
from database import (
    init_db,
    add_or_update_user,
    save_onboarding,
    activate_subscription,
    is_subscription_active,
    has_lesson_sent_today,
    unsubscribe,
    get_user,
    get_stats,
    increment_day,
    save_result,
    get_results,
    get_results_count,
)
from offers import get_offers, OFFER_TYPES
from messages import (
    format_daily_message,
    format_paywall_message,
    onboarding_result,
    WOW_HOOK_MESSAGE,
    ONBOARDING_START,
    ONBOARDING_Q2,
    ONBOARDING_Q3,
    ONBOARDING_Q4,
    ONBOARDING_Q5,
    ALREADY_SUBSCRIBED,
    UNSUBSCRIBED_MESSAGE,
    HELP_MESSAGE,
    SUBSCRIBE_MESSAGE,
    TOTAL_DAYS,
    FREE_LESSONS_COUNT,
)
from scheduler import create_scheduler

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Состояния онбординга ────────────────────────────────────────────────────
Q1, Q2, Q3, Q4, Q5 = range(5)

# Маппинг callback_data → категория ситуации
SITUATION_MAP = {
    "s_no_system":      "no_system",
    "s_losing_clients": "losing_clients",
    "s_cant_track":     "cant_track",
    "s_few_leads":      "few_leads",
}


# ─── Клавиатуры ──────────────────────────────────────────────────────────────

def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📩 Действие на сегодня"), KeyboardButton("📊 Мой прогресс")],
            [KeyboardButton("✅ Выполнено"),           KeyboardButton("📋 Мои результаты")],
            [KeyboardButton("✍️ Оффер клиенту"),      KeyboardButton("💳 Подписка")],
            [KeyboardButton("❓ Помощь")],
        ],
        resize_keyboard=True,
    )


def offer_types_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(data["label"], callback_data=f"offer_{key}")]
        for key, data in OFFER_TYPES.items()
    ])


def client_count_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("До 10",    callback_data="cnt_small")],
        [InlineKeyboardButton("10–50",    callback_data="cnt_medium")],
        [InlineKeyboardButton("50–200",   callback_data="cnt_large")],
        [InlineKeyboardButton("Более 200",callback_data="cnt_xlarge")],
    ])


def tracking_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("CRM-система",           callback_data="tr_crm")],
        [InlineKeyboardButton("Excel / таблицы",       callback_data="tr_excel")],
        [InlineKeyboardButton("Мессенджеры / заметки", callback_data="tr_chat")],
        [InlineKeyboardButton("Никак",                 callback_data="tr_none")],
    ])


def frequency_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Ежедневно",               callback_data="fr_daily")],
        [InlineKeyboardButton("Раз в неделю",            callback_data="fr_weekly")],
        [InlineKeyboardButton("Только по запросу клиента", callback_data="fr_reactive")],
        [InlineKeyboardButton("Редко или никогда",       callback_data="fr_rare")],
    ])


def difficulty_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Нет системы касаний",              callback_data="s_no_system")],
        [InlineKeyboardButton("Теряю клиентов после первой сделки", callback_data="s_losing_clients")],
        [InlineKeyboardButton("Не успеваю следить за всеми",      callback_data="s_cant_track")],
        [InlineKeyboardButton("Мало новых обращений",             callback_data="s_few_leads")],
    ])


def subscribe_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Оплатить 299 ₽/месяц", callback_data="pay_subscribe")],
        [InlineKeyboardButton("Попробовать бесплатно (3 дня)",    callback_data="pay_skip")],
    ])


# ─── Онбординг (ConversationHandler) ─────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = get_user(user.id)

    # Баг #3 исправлен: возвращающийся пользователь не теряет прогресс
    if existing and existing["onboarding_done"]:
        add_or_update_user(user.id, user.username or "", user.first_name or "Друг")
        if existing["subscribed"]:
            await update.message.reply_text(ALREADY_SUBSCRIBED, reply_markup=main_keyboard())
        else:
            await update.message.reply_text(
                "С возвращением!\n\n"
                "Рассылка снова включена. Ваш прогресс сохранён.\n"
                "Нажмите «Действие на сегодня» или /today чтобы продолжить.",
                reply_markup=main_keyboard(),
            )
        return ConversationHandler.END

    # Новый пользователь или незавершённый онбординг — начинаем заново
    add_or_update_user(user.id, user.username or "", user.first_name or "Друг")
    context.user_data.clear()
    await update.message.reply_text(ONBOARDING_START)
    return Q1


async def onboarding_q1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["niche"] = update.message.text
    await update.message.reply_text(ONBOARDING_Q2, reply_markup=client_count_keyboard())
    return Q2


async def onboarding_q2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["client_count"] = update.callback_query.data
    await update.callback_query.message.reply_text(ONBOARDING_Q3, reply_markup=tracking_keyboard())
    return Q3


async def onboarding_q3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["tracking"] = update.callback_query.data
    await update.callback_query.message.reply_text(ONBOARDING_Q4, reply_markup=frequency_keyboard())
    return Q4


async def onboarding_q4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["frequency"] = update.callback_query.data
    await update.callback_query.message.reply_text(ONBOARDING_Q5, reply_markup=difficulty_keyboard())
    return Q5


async def onboarding_q5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    situation_key = update.callback_query.data
    situation = SITUATION_MAP.get(situation_key, "no_system")

    niche = context.user_data.get("niche", "")
    save_onboarding(update.effective_user.id, niche, situation)

    result_text = onboarding_result(situation)
    await update.callback_query.message.reply_text(result_text)

    # Предложение подписки
    await update.callback_query.message.reply_text(
        "📅 Как это работает:\n\n"
        "Каждое утро в 9:00 — одно конкретное действие по работе с клиентами.\n"
        "Первые 3 дня — бесплатно.\n"
        "Дальше — подписка 299 ₽/месяц.\n\n"
        "Отмена в любой момент. Без обязательств.",
        reply_markup=subscribe_keyboard(),
    )
    return ConversationHandler.END


async def onboarding_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Онбординг прерван. Нажмите /start, чтобы начать заново.")
    return ConversationHandler.END


# ─── Подписка и оплата ───────────────────────────────────────────────────────

async def handle_subscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "pay_skip":
        user_id = update.effective_user.id
        db_user = get_user(user_id)
        if db_user:
            # Сначала WOW-хук, потом первый урок — создаёт паузу и ожидание
            await query.message.reply_text(WOW_HOOK_MESSAGE)
            first_lesson = format_daily_message(db_user["first_name"], db_user["day_index"])
            await query.message.reply_text(first_lesson, reply_markup=main_keyboard())
            increment_day(user_id)
        return

    if query.data == "pay_subscribe":
        if not PAYMENT_PROVIDER_TOKEN:
            await query.message.reply_text(
                "⚙️ Платёжный провайдер ещё не настроен.\n"
                "Свяжитесь с администратором для оформления подписки.",
            )
            return

        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title="Подписка «Бизнес-стабилизатор»",
            description=(
                "Ежедневные действия по структурированию работы с клиентами "
                "и систематизации продаж. 30 дней."
            ),
            payload="subscription_30d",
            provider_token=PAYMENT_PROVIDER_TOKEN,
            currency="RUB",
            prices=[LabeledPrice("Подписка на 30 дней", SUBSCRIPTION_PRICE_KOPECKS)],
            need_email=False,
            need_phone_number=False,
        )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload != "subscription_30d":
        await query.answer(ok=False, error_message="Неверный платёж. Попробуйте снова.")
        return
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    activate_subscription(user_id, days=SUBSCRIPTION_DAYS)
    await update.message.reply_text(
        "✅ Подписка оформлена!\n\n"
        "Теперь вы будете получать ежедневные действия\n"
        "по работе с клиентами каждое утро в 9:00.\n\n"
        "Следующий фокус придёт завтра утром.\n"
        "Используйте /today чтобы получить его прямо сейчас.",
        reply_markup=main_keyboard(),
    )
    logger.info(f"Оплата подписки: user_id={user_id}")


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_subscription_active(update.effective_user.id):
        await update.message.reply_text(
            "✅ Ваша подписка уже активна.\n"
            "Ежедневные действия приходят каждое утро в 9:00."
        )
        return
    await update.message.reply_text(SUBSCRIBE_MESSAGE, reply_markup=subscribe_keyboard())


# ─── Основные команды ─────────────────────────────────────────────────────────

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = get_user(user_id)

    if not db_user or not db_user["subscribed"]:
        await update.message.reply_text("Вы не подписаны. Нажмите /start чтобы начать.")
        return

    if not db_user["onboarding_done"]:
        await update.message.reply_text("Пожалуйста, сначала пройдите онбординг — /start")
        return

    day_index = db_user["day_index"]

    if day_index >= FREE_LESSONS_COUNT and not is_subscription_active(user_id):
        await update.message.reply_text(format_paywall_message())
        return

    # Баг #2 исправлен: первый запрос за день продвигает день,
    # повторный показывает тот же урок без продвижения (идемпотентность).
    # Это исключает дублирование, когда пользователь нажал /today до рассылки.
    if has_lesson_sent_today(user_id) and day_index > 0:
        text = format_daily_message(db_user["first_name"], day_index - 1)
        await update.message.reply_text(
            text + "\n\n📌 Это сегодняшний фокус. Следующий придёт завтра утром."
        )
    else:
        text = format_daily_message(db_user["first_name"], day_index)
        await update.message.reply_text(text)
        increment_day(user_id)


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unsubscribe(update.effective_user.id)
    await update.message.reply_text(UNSUBSCRIBED_MESSAGE)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE, reply_markup=main_keyboard())


async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = get_user(user_id)

    if not db_user:
        await update.message.reply_text("Вы ещё не начали. /start")
        return

    day = db_user["day_index"]
    pct = round((day / TOTAL_DAYS) * 100)
    bar_filled = int(pct / 10)
    bar = "🟩" * bar_filled + "⬜" * (10 - bar_filled)

    sub_status = "✅ Активна" if is_subscription_active(user_id) else f"Бесплатно ({FREE_LESSONS_COUNT - day} дней осталось)" if day < FREE_LESSONS_COUNT else "❌ Нет подписки"

    text = (
        f"📊 Ваш прогресс\n\n"
        f"Пройдено фокусов: {day} из {TOTAL_DAYS}\n"
        f"{bar} {pct}%\n\n"
        f"Подписка: {sub_status}\n\n"
        f"{'Продолжайте — система строится шаг за шагом.' if day > 0 else 'Начните прямо сейчас — /today'}"
    )
    await update.message.reply_text(text)


async def cmd_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total, active, paid = get_stats()
    await update.message.reply_text(
        f"📈 Статистика\n\n"
        f"Всего пользователей: {total}\n"
        f"Активных подписчиков: {active}\n"
        f"С оплаченной подпиской: {paid}",
    )


# ─── Офферы клиентам ─────────────────────────────────────────────────────────

async def cmd_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✍️ Готовые офферы для ваших клиентов\n\n"
        "Выберите тип сообщения — получите 3 шаблона под вашу нишу:",
        reply_markup=offer_types_keyboard(),
    )


async def handle_offer_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    offer_type = query.data.replace("offer_", "")
    user_id = update.effective_user.id
    db_user = get_user(user_id)
    niche = db_user["niche"] if db_user and db_user["niche"] else ""

    offers = get_offers(offer_type, niche)
    type_label = OFFER_TYPES.get(offer_type, {}).get("label", "Оффер")

    lines = [f"{type_label} — готовые шаблоны:\n"]
    for i, offer in enumerate(offers, 1):
        lines.append(f"Вариант {i}:\n{offer}\n")

    lines.append("💡 Замените [Имя] на имя клиента и отправляйте.")

    await query.message.reply_text("\n".join(lines))


# ─── Фиксация результата ─────────────────────────────────────────────────────

async def ask_for_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = get_user(user_id)
    day = (db_user["day_index"] - 1) if db_user and db_user["day_index"] > 0 else 0
    context.user_data["waiting_result"] = True
    context.user_data["result_day"] = day
    await update.message.reply_text(
        "Отлично! 💪\n\n"
        "📝 Напишите коротко — что получилось сегодня?\n"
        "Например: «написал 3 клиентам, двое ответили» или «настроил напоминания в CRM»"
    )


async def save_result_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result_text = update.message.text
    day = context.user_data.pop("result_day", 0)
    context.user_data.pop("waiting_result", None)

    save_result(user_id, day, result_text)
    count = get_results_count(user_id)

    if count == 1:
        streak = "Первый результат сохранён — это начало системы! 🌱"
    elif count < 5:
        streak = f"🔥 {count} результата сохранено — система строится!"
    else:
        streak = f"🔥 {count} результатов! Вы строите настоящую систему."

    await update.message.reply_text(
        f"✅ Результат сохранён!\n\n{streak}\n\n"
        "Следующий фокус придёт завтра в 9:00.\n"
        "📋 Посмотреть все результаты: /results",
        reply_markup=main_keyboard(),
    )


async def cmd_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    results = get_results(user_id)
    count = get_results_count(user_id)

    if not results:
        await update.message.reply_text(
            "📋 Результатов пока нет.\n\n"
            "После выполнения задания нажмите «✅ Выполнено» — "
            "бот запишет ваш результат.",
            reply_markup=main_keyboard(),
        )
        return

    lines = [f"📋 Ваш дневник результатов ({count} выполнено)\n"]
    for r in results:
        lines.append(f"▸ День {r['day_index'] + 1}: {r['result_text']}")

    await update.message.reply_text("\n".join(lines), reply_markup=main_keyboard())


# ─── Кнопки основного меню ───────────────────────────────────────────────────

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Ожидаем ввод результата от пользователя
    if context.user_data.get("waiting_result") and not text.startswith("/"):
        await save_result_handler(update, context)
        return

    if text == "📩 Действие на сегодня":
        await cmd_today(update, context)
    elif text == "📊 Мой прогресс":
        await cmd_progress(update, context)
    elif text == "✅ Выполнено" or "выполнил" in text.lower() or "сделал" in text.lower():
        await ask_for_result(update, context)
    elif text == "📋 Мои результаты":
        await cmd_results(update, context)
    elif text == "✍️ Оффер клиенту":
        await cmd_offers(update, context)
    elif text == "💳 Подписка":
        await cmd_subscribe(update, context)
    elif text == "❓ Помощь":
        await cmd_help(update, context)


# ─── Запуск ──────────────────────────────────────────────────────────────────

def main():
    init_db()

    async def post_init(application: Application) -> None:
        scheduler = create_scheduler(application.bot)
        scheduler.start()
        application.bot_data["scheduler"] = scheduler
        logger.info("Рассылка запланирована на %d:%02d МСК ежедневно", 9, 0)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Онбординг через ConversationHandler
    onboarding = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            Q1: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_q1)],
            Q2: [CallbackQueryHandler(onboarding_q2, pattern="^cnt_")],
            Q3: [CallbackQueryHandler(onboarding_q3, pattern="^tr_")],
            Q4: [CallbackQueryHandler(onboarding_q4, pattern="^fr_")],
            Q5: [CallbackQueryHandler(onboarding_q5, pattern="^s_")],
        },
        fallbacks=[CommandHandler("cancel", onboarding_cancel)],
        allow_reentry=True,
    )

    app.add_handler(onboarding)
    app.add_handler(CommandHandler("today",     cmd_today))
    app.add_handler(CommandHandler("stop",      cmd_stop))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("progress",  cmd_progress))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("stats",     cmd_admin_stats))
    app.add_handler(CommandHandler("results",   cmd_results))

    # Офферы
    app.add_handler(CallbackQueryHandler(handle_offer_type, pattern="^offer_"))

    # Платежи
    app.add_handler(CallbackQueryHandler(handle_subscribe_callback, pattern="^pay_"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    # Кнопки меню
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    logger.info("Бот запущен.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main()
