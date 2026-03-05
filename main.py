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

# Папка для хранения данных, которая не будет перезаписываться при деплое
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

STATS_FILE = os.path.join(DATA_DIR, "stats.json")
COMPLIMENTS_FILE = "compliments.txt"
LOVE_TASKS_FILE = "love_tasks.txt"
LUST_TASKS_FILE = "lust_tasks.txt"

# ID пользователей
MY_USER_ID = 812357068          # Ваш ID
HER_USER_ID = 1419656085        # ID вашей девушки
ALLOWED_IDS = {MY_USER_ID, HER_USER_ID}  # Множество разрешённых ID

# Список команд меню (чтобы не пересылать их как обычные сообщения)
MENU_COMMANDS = {"📊 Статистика", "🥺 Хочу комплимент", "❤️ Хочу побыть любимой", "❤️‍🔥 Хочу побыть шлюхой"}

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
        ["📊 Статистика"],
        ["🥺 Хочу комплимент"],
        ["❤️ Хочу побыть любимой"],
        ["❤️‍🔥 Хочу побыть шлюхой"],
    ],
    resize_keyboard=True,
)

# ========== Функция проверки доступа ==========
async def deny_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Проверяет, разрешён ли пользователь.
    Если нет — отправляет отказ и возвращает False.
    """
    user_id = update.effective_user.id if update.effective_user else None
    if user_id not in ALLOWED_IDS:
        # Отправляем сообщение об отказе (если есть куда)
        if update.message:
            await update.message.reply_text("Этот бот не для тебя ;)")
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("Этот бот не для тебя ;)")
        return False
    return True

# ========== Функция пересылки сообщений девушки вам (только не-команды) ==========
async def forward_to_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет копию НЕ-командного сообщения от девушки вам в личку с пометкой."""
    message = update.message
    if not message:
        return

    user = message.from_user
    if user.id != HER_USER_ID:
        return  # не от неё

    # Если это текст и он является командой меню — не пересылаем
    if message.text and message.text in MENU_COMMANDS:
        return

    # Формируем префикс с именем
    name = user.first_name or "Она"
    prefix = f"📨 От {name}:\n\n"

    # Отправляем в зависимости от типа контента
    try:
        # Текст
        if message.text:
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=prefix + message.text
            )

        # Фото
        elif message.photo:
            photo = message.photo[-1]  # самое большое
            caption = message.caption or ""
            await context.bot.send_photo(
                chat_id=MY_USER_ID,
                photo=photo.file_id,
                caption=prefix + caption
            )

        # Видео
        elif message.video:
            caption = message.caption or ""
            await context.bot.send_video(
                chat_id=MY_USER_ID,
                video=message.video.file_id,
                caption=prefix + caption
            )

        # Аудио
        elif message.audio:
            caption = message.caption or ""
            await context.bot.send_audio(
                chat_id=MY_USER_ID,
                audio=message.audio.file_id,
                caption=prefix + caption
            )

        # Голосовые
        elif message.voice:
            await context.bot.send_voice(
                chat_id=MY_USER_ID,
                voice=message.voice.file_id,
                caption=prefix + "Голосовое сообщение"
            )

        # Документы
        elif message.document:
            caption = message.caption or ""
            await context.bot.send_document(
                chat_id=MY_USER_ID,
                document=message.document.file_id,
                caption=prefix + caption
            )

        # Стикеры
        elif message.sticker:
            await context.bot.send_sticker(
                chat_id=MY_USER_ID,
                sticker=message.sticker.file_id
            )
            # Добавим текстовое уведомление
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=prefix + "Стикер"
            )

        # Видеосообщения (кружки)
        elif message.video_note:
            await context.bot.send_video_note(
                chat_id=MY_USER_ID,
                video_note=message.video_note.file_id
            )
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=prefix + "Видеосообщение (кружок)"
            )

        # Остальные типы (контакты, локации и т.п.) — просто уведомление
        else:
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=prefix + f"Отправлен {message.content_type}"
            )
    except Exception as e:
        logger.error(f"Ошибка при пересылке: {e}")

# ========== Обработчик команд ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветствие и главное меню (только для разрешённых)."""
    if not await deny_access(update, context):
        return
    await update.message.reply_text(
        "Привет, моё солнышко :)️\n"
        "Не забывай выполнять оба типа заданий, хорошо?\n\nВыбери, что ты хочешь сейчас:",
        reply_markup=main_menu_keyboard,
    )

# ========== Универсальный обработчик сообщений ==========
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все входящие сообщения: сначала пересылает (если от девушки), затем обрабатывает кнопки меню (только для разрешённых)."""
    # Сначала пересылаем не-командные сообщения девушки вам
    await forward_to_me(update, context)

    # Проверяем доступ для дальнейшей обработки (если пользователь не разрешён, отвечаем отказом)
    if not await deny_access(update, context):
        return

    # Далее обрабатываем нажатия кнопок меню (только текст)
    if update.message and update.message.text:
        text = update.message.text
        user_id = update.effective_user.id
        chat_id = str(update.effective_chat.id)

        if text == "📊 Статистика":
            stats = load_stats()
            user_stats = stats.get(chat_id, {"love": 0, "lust": 0})
            await update.message.reply_text(
                f"📊 Твоя статистика\n"
                f"Любовь — {user_stats['love']}\n"
                f"Похоть — {user_stats['lust']}",
                reply_markup=main_menu_keyboard,
            )
            # Если это сделала девушка — уведомить меня
            if user_id == HER_USER_ID:
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"📊 Она запросила статистику:\nЛюбовь: {user_stats['love']}\nПохоть: {user_stats['lust']}"
                )

        elif text == "🥺 Хочу комплимент":
            compliment = random.choice(compliments)
            await update.message.reply_text(compliment, reply_markup=main_menu_keyboard)
            # Если это сделала девушка — уведомить меня
            if user_id == HER_USER_ID:
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"💬 Она получила комплимент:\n\n{compliment}"
                )

        elif text == "❤️ Хочу побыть любимой":
            task_text, price = random.choice(love_tasks)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Сделала это", callback_data=f"love_done_{price}"),
                    InlineKeyboardButton("❌ Не хочу", callback_data="love_cancel"),
                ]
            ])
            await update.message.reply_text(task_text, reply_markup=keyboard)

        elif text == "❤️‍🔥 Хочу побыть шлюхой":
            task_text, price = random.choice(lust_tasks)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Сделала это", callback_data=f"lust_done_{price}"),
                    InlineKeyboardButton("❌ Не хочу", callback_data="lust_cancel"),
                ]
            ])
            await update.message.reply_text(task_text, reply_markup=keyboard)

# ========== Обработчик инлайн-кнопок ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на инлайн-кнопки (только для разрешённых)."""
    if not await deny_access(update, context):
        # Важно: для callback нужно обязательно ответить, чтобы убрать "часики"
        if update.callback_query:
            await update.callback_query.answer()
        return

    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id
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

        # Отправляем подтверждение девушке
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к любви, сделав это:\n\n{task_text}",
            reply_markup=main_menu_keyboard,
        )

        # Если это сделала девушка — уведомить меня
        if user_id == HER_USER_ID:
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"✅ Она выполнила задание «{task_text}» и получила +{price} к любви."
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

        if user_id == HER_USER_ID:
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"🔥 Она выполнила задание «{task_text}» и получила +{price} к похоти."
            )

    elif data in ("love_cancel", "lust_cancel"):
        # Просто удаляем сообщение
        await message.delete()

        # Уведомить меня, если это сделала девушка
        if user_id == HER_USER_ID:
            # Определяем тип задания из callback_data
            task_type = "любви" if data == "love_cancel" else "похоти"
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"❌ Она отказалась делать задание «{task_text}» (тип: {task_type})."
            )

# ========== Запуск бота ==========
def main() -> None:
    if not TOKEN:
        logger.error("Токен бота не задан! Установите переменную окружения BOT_TOKEN.")
        return

    app = Application.builder().token(TOKEN).build()

    # Порядок важен: сначала команда /start
    app.add_handler(CommandHandler("start", start))
    # Потом обработчик всех сообщений (включая текст, фото, видео и т.д.)
    app.add_handler(MessageHandler(filters.ALL, handle_all_messages))
    # Обработчик инлайн-кнопок
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()