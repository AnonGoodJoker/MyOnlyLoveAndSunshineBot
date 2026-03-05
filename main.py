import json
import random
import logging
import os
from typing import Dict, List, Tuple

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== Конфигурация ==========
TOKEN = os.getenv("BOT_TOKEN")
STATS_FILE = "stats.json"
COMPLIMENTS_FILE = "compliments.txt"
LOVE_TASKS_FILE = "love_tasks.txt"
LUST_TASKS_FILE = "lust_tasks.txt"

# ========== Загрузка данных из файлов ==========
def load_lines(filename: str) -> list:
    """Загружает строки из файла, убирая пустые и лишние пробелы."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines
    except FileNotFoundError:
        logger.warning(f"Файл {filename} не найден, создаю пустой список.")
        return []

def load_tasks(filename: str) -> List[Tuple[str, int]]:
    """
    Загружает задания из файла.
    Каждая строка может быть в формате "Текст задания|Цена".
    Если цена не указана, по умолчанию = 1.
    Возвращает список кортежей (текст, цена).
    """
    tasks = []
    lines = load_lines(filename)
    for line in lines:
        if '|' in line:
            parts = line.split('|', 1)
            text = parts[0].strip()
            try:
                price = int(parts[1].strip())
            except ValueError:
                logger.warning(f"Неверный формат цены в строке: {line}, используется цена 1")
                price = 1
        else:
            text = line
            price = 1
        tasks.append((text, price))
    return tasks

def load_stats() -> Dict[str, Dict[str, int]]:
    """Загружает статистику из JSON-файла."""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(stats: Dict[str, Dict[str, int]]) -> None:
    """Сохраняет статистику в JSON-файл."""
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

# ========== Глобальные списки ==========
compliments = load_lines(COMPLIMENTS_FILE)
love_tasks = load_tasks(LOVE_TASKS_FILE)
lust_tasks = load_tasks(LUST_TASKS_FILE)

# Проверка, что списки не пусты
if not compliments:
    compliments = ["Ты прекрасна!"]
if not love_tasks:
    love_tasks = [("Скажи, что любишь меня.", 1)]
if not lust_tasks:
    lust_tasks = [("Пофлиртуй с кем-то и отправь пруфы.", 1)]

# ========== Клавиатура главного меню ==========
main_menu_keyboard = ReplyKeyboardMarkup(
    [
        ["Статистика"],
        ["Хочу комплимент"],
        ["Хочу побыть любимой"],
        ["Хочу побыть шлюхой"],
    ],
    resize_keyboard=True,
)

# ========== Обработчики команд ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветствие и главное меню."""
    await update.message.reply_text(
        "Привет, моё солнышко :)️\n"
        "Не забывай выполнять оба типа заданий, хорошо?\n\nВыбери, что ты хочешь сейчас:",
        reply_markup=main_menu_keyboard,
    )

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на кнопки главного меню."""
    text = update.message.text
    chat_id = str(update.effective_chat.id)

    if text == "Статистика":
        stats = load_stats()
        user_stats = stats.get(chat_id, {"love": 0, "lust": 0})
        await update.message.reply_text(
            f"📊 Твоя статистика:\n"
            f"Любовь: {user_stats['love']}\n"
            f"Похоть: {user_stats['lust']}",
            reply_markup=main_menu_keyboard,
        )

    elif text == "Хочу комплимент":
        compliment = random.choice(compliments)
        await update.message.reply_text(compliment, reply_markup=main_menu_keyboard)

    elif text == "Хочу побыть любимой":
        task_text, price = random.choice(love_tasks)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Сделала это", callback_data=f"love_done_{price}"),
                InlineKeyboardButton("❌ Не хочу", callback_data="love_cancel"),
            ]
        ])
        await update.message.reply_text(task_text, reply_markup=keyboard)

    elif text == "Хочу побыть шлюхой":
        task_text, price = random.choice(lust_tasks)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Сделала это", callback_data=f"lust_done_{price}"),
                InlineKeyboardButton("❌ Не хочу", callback_data="lust_cancel"),
            ]
        ])
        await update.message.reply_text(task_text, reply_markup=keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = str(update.effective_chat.id)
    message = query.message
    task_text = message.text  # текст задания

    if data.startswith("love_done_"):
        # Извлекаем цену
        try:
            price = int(data.split("_")[2])
        except (IndexError, ValueError):
            logger.error(f"Не удалось извлечь цену из callback_data: {data}")
            price = 1  # на всякий случай

        # Обновляем статистику
        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0}
        stats[chat_id]["love"] += price
        save_stats(stats)

        # Удаляем сообщение с заданием
        await message.delete()

        # Отправляем подтверждение
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к любви, сделав это:\n\n{task_text}",
            reply_markup=main_menu_keyboard,
        )

    elif data.startswith("lust_done_"):
        try:
            price = int(data.split("_")[2])
        except (IndexError, ValueError):
            logger.error(f"Не удалось извлечь цену из callback_data: {data}")
            price = 1

        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0}
        stats[chat_id]["lust"] += price
        save_stats(stats)

        await message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к похоти, сделав это:\n\n{task_text}",
            reply_markup=main_menu_keyboard,
        )

    elif data in ("love_cancel", "lust_cancel"):
        # Просто удаляем сообщение
        await message.delete()

# ========== Запуск бота ==========
def main() -> None:
    if not TOKEN:
        logger.error("Токен бота не задан! Установите переменную окружения BOT_TOKEN.")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()