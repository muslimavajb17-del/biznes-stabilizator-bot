import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DAILY_HOUR = int(os.getenv("DAILY_HOUR", "9"))
DAILY_MINUTE = int(os.getenv("DAILY_MINUTE", "0"))

# Платёжный токен от @BotFather (Telegram Payments)
# Для тестов используйте: PROVIDER_TOKEN=PAYMENT_PROVIDER_TOKEN_TEST
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")

# Цена подписки в копейках (299 ₽ = 29900 копеек)
SUBSCRIPTION_PRICE_KOPECKS = int(os.getenv("SUBSCRIPTION_PRICE", "29900"))
SUBSCRIPTION_DAYS = 30

DB_PATH = os.getenv("DB_PATH", "users.db")
