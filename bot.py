import os
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
import matplotlib.pyplot as plt
import random

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

TOKEN = os.getenv("TOKEN")
WEBHOOK_PATH = "/webhook"

WIFE_ID = 1253947361
HUSBAND_ID = 397515395

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- База ---
conn = sqlite3.connect("income.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS income (
    amount REAL,
    percent REAL,
    date TEXT
)
""")
conn.commit()

# --- Кнопки ---
wife_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="➕ Добавить доход")]],
    resize_keyboard=True
)

husband_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статистика за день")],
        [KeyboardButton(text="📊 Статистика за неделю")],
        [KeyboardButton(text="📊 Статистика за месяц")],
        [KeyboardButton(text="📊 Общая статистика")]
    ],
    resize_keyboard=True
)

# --- Фразы для подтверждения дохода ---
phrases = [
    "Доход добавлен.",
    "Запись успешно внесена.",
    "Сумма учтена."
]

# --- Старт ---
@dp.message(Command("start"))
async def start(message: types.Message):
    if message.from_user.id == WIFE_ID:
        await message.answer("Готов к работе.", reply_markup=wife_kb)
    elif message.from_user.id == HUSBAND_ID:
        await message.answer("Выберите период статистики:", reply_markup=husband_kb)

# --- Кнопки статистики ---
@dp.message(lambda m: m.text.startswith("📊"))
async def stats_buttons(message: types.Message):
    if message.from_user.id != HUSBAND_ID:
        return

    period_map = {
        "📊 Статистика за день": "day",
        "📊 Статистика за неделю": "week",
        "📊 Статистика за месяц": "month",
        "📊 Общая статистика": "all"
    }
    period = period_map.get(message.text, "all")
    await send_statistics(user_id=HUSBAND_ID, period=period)

# --- Добавление дохода ---
@dp.message()
async def handle_income(message: types.Message):
    if message.from_user.id != WIFE_ID:
        return

    # Игнорируем кнопки статистики
    if message.text.startswith("📊"):
        return

    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Это не число, попробуйте ещё раз:")
        return

    percent = round(amount * 0.4, 2)
    date = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("INSERT INTO income VALUES (?, ?, ?)", (amount, percent, date))
    conn.commit()

    await message.answer(f"{random.choice(phrases)}\n40%: {percent:.2f} ₽", reply_markup=wife_kb)
    await send_statistics(HUSBAND_ID, period="all", new_income=(amount, percent))

# --- Функция отправки статистики ---
async def send_statistics(user_id, period="all", new_income=None):
    today = datetime.now().date()

    if period == "day":
        start_date = today
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
    elif period == "month":
        start_date = today.replace(day=1)
    else:
        start_date = None

    if start_date:
        cursor.execute("SELECT amount, percent, date FROM income WHERE date >= ?", (start_date.strftime("%Y-%m-%d"),))
    else:
        cursor.execute("SELECT amount, percent, date FROM income")
    data = cursor.fetchall()

    total = sum(row[0] for row in data)
    total_percent = sum(row[1] for row in data)
    count = len(data)
    average = total / count if count else 0

    lines = []
    if new_income:
        lines.append(f"Новый доход: {new_income[0]:.2f} ₽ (40%: {new_income[1]:.2f} ₽)")

    lines += [
        f"Всего записей: {count}",
        f"Общий доход: {total:.2f} ₽",
        f"Общий 40%: {total_percent:.2f} ₽",
        f"Средний доход: {average:.2f} ₽"
    ]

    await bot.send_message(user_id, "\n".join(lines))

    # --- График ---
    if count:
        dates = [datetime.strptime(row[2], "%Y-%m-%d").date() for row in data]
        amounts = [row[0] for row in data]
        percents = [row[1] for row in data]

        plt.figure(figsize=(6, 4))
        plt.plot(dates, amounts, marker='o', label='Доход')
        plt.plot(dates, percents, marker='x', linestyle='--', label='40% дохода')
        plt.title("Доходы")
        plt.xlabel("Дата")
        plt.ylabel("Сумма, ₽")
        plt.legend()
        plt.grid(True)

        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        await bot.send_photo(user_id, buf)

# --- Вебхук ---
async def on_startup(app):
    url = os.getenv("RENDER_EXTERNAL_URL")
    await bot.set_webhook(f"{url}{WEBHOOK_PATH}")

def main():
    app = web.Application()
    SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()
