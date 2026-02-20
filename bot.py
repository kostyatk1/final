import os
import json
from datetime import datetime, timedelta
from io import BytesIO
import matplotlib.pyplot as plt

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web


TOKEN = os.getenv("TOKEN")
WEBHOOK_PATH = "/webhook"

WIFE_ID = 1253947361
HUSBAND_ID = 397515395

RESET_PASSWORD = "1488"
awaiting_reset_password = set()

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ================= GOOGLE SHEETS =================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.getenv("GOOGLE_CREDS_JSON"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("IncomeBot").sheet1

# =================================================


# ================= КНОПКИ =================

wife_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="➕ Добавить доход")]],
    resize_keyboard=True
)

husband_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статистика за день")],
        [KeyboardButton(text="📊 Статистика за неделю")],
        [KeyboardButton(text="📊 Статистика за месяц")],
        [KeyboardButton(text="📊 Общая статистика")],
        [KeyboardButton(text="🗑 Сбросить статистику")]
    ],
    resize_keyboard=True
)

# =================================================


@dp.message(Command("start"))
async def start(message: types.Message):
    if message.from_user.id == WIFE_ID:
        await message.answer("Введите доход.", reply_markup=wife_kb)
    elif message.from_user.id == HUSBAND_ID:
        await message.answer("Выберите действие:", reply_markup=husband_kb)


# ================= ДОБАВЛЕНИЕ ДОХОДА =================

@dp.message(lambda m: m.text == "➕ Добавить доход")
async def ask_income(message: types.Message):
    if message.from_user.id == WIFE_ID:
        await message.answer("Введите сумму:")


@dp.message()
async def handle_messages(message: types.Message):

    # ===== СБРОС =====
    if message.from_user.id == HUSBAND_ID:

        if message.text == "🗑 Сбросить статистику":
            awaiting_reset_password.add(HUSBAND_ID)
            await message.answer("Введите пароль для подтверждения:")
            return

        if message.from_user.id in awaiting_reset_password:
            if message.text == RESET_PASSWORD:
                sheet.resize(rows=1)  # Оставляем только заголовки
                awaiting_reset_password.remove(HUSBAND_ID)
                await message.answer("Статистика полностью очищена.", reply_markup=husband_kb)
            else:
                awaiting_reset_password.remove(HUSBAND_ID)
                await message.answer("Неверный пароль.", reply_markup=husband_kb)
            return

    # ===== ДОБАВЛЕНИЕ ДОХОДА =====
    if message.from_user.id == WIFE_ID:

        if message.text.startswith("📊"):
            return

        try:
            amount = float(message.text.replace(",", "."))
        except:
            await message.answer("Это не число.")
            return

        percent = round(amount * 0.4, 2)
        date = datetime.now().strftime("%Y-%m-%d")

        sheet.append_row([amount, percent, date])

        await message.answer(
            f"Добавлено.\n40%: {percent:.2f} ₽",
            reply_markup=wife_kb
        )

        await send_statistics(HUSBAND_ID, "all", new_income=(amount, percent))
        return

    # ===== КНОПКИ СТАТИСТИКИ =====
    if message.from_user.id == HUSBAND_ID and message.text.startswith("📊"):
        period_map = {
            "📊 Статистика за день": "day",
            "📊 Статистика за неделю": "week",
            "📊 Статистика за месяц": "month",
            "📊 Общая статистика": "all"
        }
        period = period_map.get(message.text, "all")
        await send_statistics(HUSBAND_ID, period)


# ================= СТАТИСТИКА =================

async def send_statistics(user_id, period="all", new_income=None):
    rows = sheet.get_all_records()
    today = datetime.now().date()

    if period == "day":
        rows = [
            r for r in rows
            if datetime.strptime(r["date"], "%Y-%m-%d").date() == today
        ]

    elif period == "week":
        start_week = today - timedelta(days=today.weekday())
        rows = [
            r for r in rows
            if datetime.strptime(r["date"], "%Y-%m-%d").date() >= start_week
        ]

    elif period == "month":
        rows = [
            r for r in rows
            if datetime.strptime(r["date"], "%Y-%m-%d").date().month == today.month
            and datetime.strptime(r["date"], "%Y-%m-%d").date().year == today.year
        ]

    total = sum(float(r["amount"]) for r in rows)
    total_percent = sum(float(r["percent"]) for r in rows)
    count = len(rows)
    average = total / count if count else 0

    lines = []

    if new_income:
        lines.append(
            f"Новый доход: {new_income[0]:.2f} ₽ (40%: {new_income[1]:.2f} ₽)"
        )

    lines += [
        f"Записей: {count}",
        f"Общий доход: {total:.2f} ₽",
        f"Общий 40%: {total_percent:.2f} ₽",
        f"Средний доход: {average:.2f} ₽"
    ]

    await bot.send_message(user_id, "\n".join(lines))

    if count:
        dates = [datetime.strptime(r["date"], "%Y-%m-%d").date() for r in rows]
        amounts = [float(r["amount"]) for r in rows]

        plt.figure(figsize=(6, 4))
        plt.plot(dates, amounts, marker='o')
        plt.title("Доход")
        plt.xlabel("Дата")
        plt.ylabel("Сумма, ₽")
        plt.grid(True)

        buf = BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        await bot.send_photo(user_id, buf)


# ================= WEBHOOK =================

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
