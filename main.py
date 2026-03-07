import json
import base64
import random
import logging
import os
from datetime import time, datetime, timedelta
from typing import Dict, List, Tuple

import pytz
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Глобальный список времён вызовов (не используется, но оставлен для совместимости)
CHALLENGE_TIMES = []

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
REWARDS_FILE = "rewards.txt"

# ID пользователей
MY_USER_ID = 812357068          # Ваш ID
HER_USER_ID = 1419656085        # ID вашей девушки
ALLOWED_IDS = {MY_USER_ID, HER_USER_ID}  # Множество разрешённых ID

# Интервал вызовов (в часах)
CHALLENGE_INTERVAL_HOURS = 3  # Можете изменить на любое целое число

# Часовой пояс Екатеринбурга (UTC+5)
TIMEZONE = pytz.timezone('Asia/Yekaterinburg')

# Список команд меню (чтобы не пересылать их как обычные сообщения)
MENU_COMMANDS = {
    "📊 Статистика",
    "🥺 Хочу комплимент",
    "❤️ Хочу побыть любимой",
    "❤️‍🔥 Хочу побыть шлюхой",
    "🛍 Магазин"
}

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

def load_rewards(filename: str) -> List[Tuple[str, int]]:
    """Загружает награды из файла (аналогично load_tasks)."""
    return load_tasks(filename)

def load_stats() -> Dict[str, Dict[str, int]]:
    """
    Загружает статистику, принудительно исправляя Base64 на JSON при чтении.
    """
    if not os.path.exists(STATS_FILE) or os.path.getsize(STATS_FILE) == 0:
        return {}

    with open(STATS_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Если это Base64 (нет фигурных скобок), декодируем
    if content and not content.startswith('{'):
        try:
            decoded_json = base64.b64decode(content).decode('utf-8')
            stats = json.loads(decoded_json)
            
            # Агрессивно перезаписываем файл нормальным JSON сразу, 
            # чтобы хостинг больше не "пугался" этого файла
            with open(STATS_FILE, "w", encoding="utf-8") as f_out:
                json.dump(stats, f_out, indent=2, ensure_ascii=False)
            logger.info("Файл был в Base64, успешно сконвертирован в чистый JSON.")
        except Exception as e:
            logger.error(f"Ошибка при конвертации Base64: {e}")
            return {}
    else:
        # Если это нормальный JSON, просто парсим
        try:
            stats = json.loads(content)
        except json.JSONDecodeError:
            return {}

    # Убеждаемся, что есть поле 'spent'
    for chat_id in stats:
        if not isinstance(stats[chat_id], dict):
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0}
        if 'spent' not in stats[chat_id]:
            stats[chat_id]['spent'] = 0
            
    return stats


def save_stats(stats: Dict[str, Dict[str, int]]) -> None:
    """Сохраняет статистику в JSON-файл."""
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

# ========== Глобальные списки ==========
compliments = load_lines(COMPLIMENTS_FILE)
love_tasks = load_tasks(LOVE_TASKS_FILE)
lust_tasks = load_tasks(LUST_TASKS_FILE)
rewards = load_rewards(REWARDS_FILE)  # список кортежей (название, цена)

# Проверка, что списки не пусты
if not compliments:
    compliments = ["Ты прекрасна!"]
if not love_tasks:
    love_tasks = [("Скажи, что любишь меня.", 1)]
if not lust_tasks:
    lust_tasks = [("Пофлиртуй с кем-то и отправь пруфы.", 1)]
if not rewards:
    rewards = [("Нет доступных наград", 1)]

# ========== Клавиатура главного меню ==========
main_menu_keyboard = ReplyKeyboardMarkup(
    [
        ["📊 Статистика"],
        ["🥺 Хочу комплимент"],
        ["❤️ Хочу побыть любимой"],
        ["❤️‍🔥 Хочу побыть шлюхой"],
        ["🛍 Магазин"],
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

# Команда: следующий вызов
async def next_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает, через сколько времени будет следующий вызов (по времени Екатеринбурга)."""
    if not await deny_access(update, context):
        return

    logger.info("Команда /next_challenge вызвана")

    # Получаем список часов вызовов из bot_data
    challenge_hours = context.bot_data.get('challenge_hours', [])
    if not challenge_hours:
        await update.message.reply_text("❌ Список часов вызовов не инициализирован. Проверьте логи бота.")
        return

    try:
        now = datetime.now(TIMEZONE)
        current_hour = now.hour
        current_minute = now.minute

        # Ищем следующий час вызова
        next_hour = None
        for hour in challenge_hours:
            if hour > current_hour:
                next_hour = hour
                break
            elif hour == current_hour and current_minute == 0:
                # Если сейчас ровно час вызова, считаем, что вызов уже был, берём следующий
                continue

        if next_hour is None:
            # Берём первый час следующих суток
            next_hour = challenge_hours[0] + 24

        # Определяем дату следующего вызова
        next_date = now.date()
        if next_hour >= 24:
            next_hour -= 24
            next_date += timedelta(days=1)

        next_time = TIMEZONE.localize(datetime.combine(next_date, time(next_hour, 0)))

        delta = next_time - now
        hours, remainder = divmod(delta.seconds, 3600)
        minutes = remainder // 60

        await update.message.reply_text(
            f"⏳ Следующий вызов через {hours} ч {minutes} мин (в {next_time.strftime('%H:%M')} по Екатеринбургу)."
        )
    except Exception as e:
        logger.exception("Ошибка в /next_challenge")
        await update.message.reply_text("Произошла внутренняя ошибка. Подробности в логах.")

# Команда: принудительный вызов (только для автора)
async def force_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принудительно отправить вызов (только для создателя)."""
    if update.effective_user.id != MY_USER_ID:
        await update.message.reply_text("Эта команда только для создателя.")
        return
    # Вызываем функцию отправки вызова
    await send_challenge(context)
    await update.message.reply_text("✅ Вызов принудительно отправлен!")

# Новая команда: добавление очков (только для автора) с возможной причиной
async def add_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавляет очки девушке (только для автора). Использование: /addscore love 10 [причина]"""
    if update.effective_user.id != MY_USER_ID:
        await update.message.reply_text("Эта команда только для создателя.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Использование: /addscore love <число> [причина]")
        return
    score_type = context.args[0].lower()
    if score_type not in ('love', 'lust'):
        await update.message.reply_text("Тип должен быть love или lust.")
        return
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Количество должно быть целым числом.")
        return
    if amount <= 0:
        await update.message.reply_text("Количество должно быть положительным.")
        return

    # Загружаем статистику для девушки
    stats = load_stats()
    her_chat_id = str(HER_USER_ID)
    if her_chat_id not in stats:
        stats[her_chat_id] = {"love": 0, "lust": 0, "spent": 0}
    stats[her_chat_id][score_type] += amount
    save_stats(stats)

    # Русское название
    type_name = {'love': 'любви', 'lust': 'похоти'}.get(score_type, score_type)

    # Причина (если указана)
    reason = None
    if len(context.args) > 2:
        reason = ' '.join(context.args[2:])

    # Сообщение девушке
    if reason:
        await context.bot.send_message(
            chat_id=HER_USER_ID,
            text=f"Ты дополнительно получила +{amount} очков {type_name} по следующей причине: {reason}"
        )
    else:
        await context.bot.send_message(
            chat_id=HER_USER_ID,
            text=f"Ты дополнительно получила +{amount} очков {type_name}!"
        )

    # Подтверждение автору
    await update.message.reply_text(f"✅ Добавлено +{amount} к очкам {type_name} для девушки.")

# ========== Функция отображения магазина с пагинацией ==========
async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """Отправляет сообщение со списком наград и кнопками пагинации/покупки."""
    items_per_page = 5
    total_pages = (len(rewards) + items_per_page - 1) // items_per_page
    page = max(0, min(page, total_pages - 1))

    start = page * items_per_page
    end = start + items_per_page
    current_items = rewards[start:end]

    # Формируем текст
    text = f"🛍 Магазин (страница {page+1}/{total_pages}):\n\n"
    for idx, (name, cost) in enumerate(current_items, start=start+1):
        text += f"{idx}. {name} — {cost} баллов\n"

    # Создаём инлайн-кнопки
    keyboard = []
    # Кнопки для каждой награды
    for i, (name, cost) in enumerate(current_items):
        actual_index = start + i  # глобальный индекс
        keyboard.append([InlineKeyboardButton(
            f"✅ {name} ({cost})",
            callback_data=f"buy_{actual_index}_{cost}"
        )])

    # Кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"shop_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Вперёд", callback_data=f"shop_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка закрытия (необязательно)
    keyboard.append([InlineKeyboardButton("❌ Закрыть", callback_data="shop_close")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

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
            user_stats = stats.get(chat_id, {"love": 0, "lust": 0, "spent": 0})
            total_earned = user_stats['love'] + user_stats['lust']
            # Новый расчёт баланса: min(любовь, похоть) - потрачено
            current_balance = min(user_stats['love'], user_stats['lust']) - user_stats.get('spent', 0)
            await update.message.reply_text(
                f"📊 Твоя статистика:\n"
                f"Всего заработано: {total_earned}\n"
                f"Текущий баланс: {current_balance}\n\n"
                f"(Любовь: {user_stats['love']}, Похоть: {user_stats['lust']})",
                reply_markup=main_menu_keyboard,
            )
            # Если это сделала девушка — уведомить меня
            if user_id == HER_USER_ID:
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"📊 Она запросила статистику:\n"
                         f"Всего заработано: {total_earned}\n"
                         f"Текущий баланс: {current_balance}\n"
                         f"Любовь: {user_stats['love']}, Похоть: {user_stats['lust']}"
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

        elif text == "🛍 Магазин":
            await show_shop(update, context, page=0)

# ========== Функция отправки вызова по расписанию ==========
async def send_challenge(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет вызов (удвоенное задание) в запланированное время."""
    chat_id = HER_USER_ID
    bot_data = context.bot_data

    # Удаляем предыдущий активный вызов, если есть
    if 'challenge_message_id' in bot_data and 'challenge_chat_id' in bot_data:
        try:
            await context.bot.delete_message(
                chat_id=bot_data['challenge_chat_id'],
                message_id=bot_data['challenge_message_id']
            )
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущее сообщение вызова: {e}")
        # Очищаем старые данные
        for key in ['challenge_message_id', 'challenge_chat_id', 'challenge_task_text', 'challenge_price', 'challenge_type']:
            bot_data.pop(key, None)

    # Выбираем случайный тип задания и само задание
    task_type = random.choice(['love', 'lust'])
    if task_type == 'love':
        task_text, price = random.choice(love_tasks)
    else:
        task_text, price = random.choice(lust_tasks)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Выполнила", callback_data=f"challenge_{task_type}_done_{price}"),
            InlineKeyboardButton("❌ Пропустить", callback_data="challenge_skip")
        ]
    ])

    message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚡️ ВЫЗОВ ⚡️\n\n{task_text}\n\nЭто вызов с ограниченным временем, награда x3!\n\nЕсли ты его выполнишь, получишь +{price*3} к {task_type}!\nЕсли справишься лучше чем нужно, я докину баллов за старания!\n\nНе забывай, что у тебя всего 3 часа, чтобы выполнить его, хорошо?",
        reply_markup=keyboard
    )

    # Сохраняем информацию о вызове (цена и тип не сохраняются – будут взяты из callback_data)
    bot_data['challenge_message_id'] = message.message_id
    bot_data['challenge_chat_id'] = chat_id
    bot_data['challenge_task_text'] = task_text

    # Уведомляем вас
    await context.bot.send_message(
        chat_id=MY_USER_ID,
        text=f"⚡️ Новый вызов для неё:\n\n{task_text} (тип: {task_type}, базовые очки: {price})"
    )

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

    # --- Обычные задания (любовь/похоть) ---
    if data.startswith("love_done_"):
        try:
            price = int(data.split("_")[2])
        except (IndexError, ValueError):
            logger.error(f"Не удалось извлечь цену из callback_data: {data}")
            price = 1

        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0}
        stats[chat_id]["love"] += price
        save_stats(stats)

        await message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к любви, сделав это:\n\n{message.text}",
            reply_markup=main_menu_keyboard,
        )

        if user_id == HER_USER_ID:
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"✅ Она выполнила задание «{message.text}» и получила +{price} к любви."
            )
        return

    elif data.startswith("lust_done_"):
        try:
            price = int(data.split("_")[2])
        except (IndexError, ValueError):
            price = 1

        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0}
        stats[chat_id]["lust"] += price
        save_stats(stats)

        await message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к похоти, сделав это:\n\n{message.text}",
            reply_markup=main_menu_keyboard,
        )

        if user_id == HER_USER_ID:
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"🔥 Она выполнила задание «{message.text}» и получила +{price} к похоти."
            )
        return

    elif data in ("love_cancel", "lust_cancel"):
        await message.delete()
        if user_id == HER_USER_ID:
            task_type = "любви" if data == "love_cancel" else "похоти"
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"❌ Она отказалась делать задание «{message.text}» (тип: {task_type})."
            )
        return

    # --- Вызовы ---
    if data.startswith("challenge_"):
        # Проверяем, есть ли активный вызов в bot_data
        if 'challenge_message_id' not in context.bot_data or context.bot_data['challenge_message_id'] != message.message_id:
            # Сообщение устарело или бот перезапущен
            await message.delete()
            await query.answer("Этот вызов уже недействителен.", show_alert=True)
            return

        # Получаем данные из callback_data
        parts = data.split('_')
        if len(parts) >= 4 and parts[0] == 'challenge' and parts[2] == 'done':
            # Формат: challenge_love_done_2
            challenge_type = parts[1]  # 'love' или 'lust'
            try:
                price = int(parts[3])
            except ValueError:
                price = 1
        else:
            # Это challenge_skip
            challenge_type = None
            price = 0

        # Получаем текст задания из bot_data
        challenge_task_text = context.bot_data.get('challenge_task_text', 'Неизвестное задание')

        if data == "challenge_skip":
            await message.delete()
            for key in ['challenge_message_id', 'challenge_chat_id', 'challenge_task_text']:
                context.bot_data.pop(key, None)
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"❌ Она пропустила вызов: «{challenge_task_text}»."
            )
            return

        # Выполнение вызова
        tripled_price = price * 3

        # Русское название типа
        type_name = {'love': 'любви', 'lust': 'похоти'}.get(challenge_type, challenge_type)

        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0}
        stats[chat_id][challenge_type] += tripled_price
        save_stats(stats)

        await message.delete()
        for key in ['challenge_message_id', 'challenge_chat_id', 'challenge_task_text']:
            context.bot_data.pop(key, None)

        # Подтверждение девушке
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚡️ВЫЗОВ ВСЁ⚡️ Ты выполнила вызов и получила x3 баллов: +{tripled_price} к {type_name}!",
            reply_markup=main_menu_keyboard
        )

        # Уведомление вам
        await context.bot.send_message(
            chat_id=MY_USER_ID,
            text=f"⚡️ Она выполнила вызов: «{challenge_task_text}» и получила +{tripled_price} к очкам {type_name} (x3 от {price})."
        )
        return

    # --- Магазин ---
    if data.startswith("buy_"):
        # Формат: buy_<index>_<price>
        parts = data.split('_')
        if len(parts) != 3:
            await query.answer("Ошибка: неверный формат.", show_alert=True)
            return
        try:
            idx = int(parts[1])
            cost = int(parts[2])
        except ValueError:
            await query.answer("Ошибка: неверные данные.", show_alert=True)
            return

        if idx < 0 or idx >= len(rewards):
            await query.answer("Награда не найдена.", show_alert=True)
            return

        reward_name, reward_cost = rewards[idx]
        if reward_cost != cost:
            await query.answer("Цена изменилась, попробуйте снова.", show_alert=True)
            return

        # Загружаем статистику
        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0}
        user_stats = stats[chat_id]

        # Вычисляем баланс по новому правилу
        current_balance = min(user_stats['love'], user_stats['lust']) - user_stats.get('spent', 0)

        if current_balance < cost:
            # Недостаточно баллов
            await query.answer("❌ Недостаточно баллов! Подкопи их, выполняя задания, хорошо?", show_alert=True)
            if user_id == HER_USER_ID:
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"❌ Она пыталась купить «{reward_name}» за {cost} баллов, но у неё недостаточно (баланс {current_balance})."
                )
            return

        # Достаточно баллов — списываем
        stats[chat_id]['spent'] = stats[chat_id].get('spent', 0) + cost
        save_stats(stats)

        # Сообщение девушке
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Ты купила награду: «{reward_name}» за {cost} баллов!",
            reply_markup=main_menu_keyboard
        )

        # Уведомление вам
        # После покупки обновляем баланс для сообщения вам
        new_balance = min(user_stats['love'], user_stats['lust']) - stats[chat_id]['spent']
        await context.bot.send_message(
            chat_id=MY_USER_ID,
            text=f"✅ Она купила награду: «{reward_name}» за {cost} баллов. Текущий баланс: {new_balance}"
        )

        # Закрываем сообщение магазина (удаляем или обновляем)
        await message.delete()
        return

    if data.startswith("shop_page_"):
        try:
            page = int(data.split("_")[2])
        except (IndexError, ValueError):
            await query.answer("Ошибка страницы.", show_alert=True)
            return
        await show_shop(update, context, page)
        return

    if data == "shop_close":
        await message.delete()
        return

# ========== Запуск бота ==========
def main() -> None:
    if not TOKEN:
        logger.error("Токен бота не задан! Установите переменную окружения BOT_TOKEN.")
        return

    app = Application.builder().token(TOKEN).build()

    # Генерируем список часов вызовов (целые числа) для команды next_challenge
    challenge_hours = list(range(0, 24, CHALLENGE_INTERVAL_HOURS))
    app.bot_data['challenge_hours'] = challenge_hours

    # Генерируем список времен для планировщика (с таймзоной)
    challenge_times_local = []
    for hour in challenge_hours:
        t = time(hour=hour, minute=0, second=0, tzinfo=TIMEZONE)
        challenge_times_local.append(t)

    app.bot_data['challenge_times'] = challenge_times_local
    global CHALLENGE_TIMES
    CHALLENGE_TIMES = challenge_times_local

    # Настройка планировщика заданий
    job_queue = app.job_queue
    if job_queue:
        for t in challenge_times_local:
            job_queue.run_daily(send_challenge, time=t, days=(0,1,2,3,4,5,6), name=f"challenge_{t.hour:02d}")
        logger.info(f"Планировщик вызовов запущен: каждый день в {[t.strftime('%H:%M') for t in challenge_times_local]} по Екатеринбургу")
    else:
        logger.warning("Job queue не доступна, вызовы не будут отправляться автоматически.")

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next_challenge", next_challenge))
    app.add_handler(CommandHandler("force_challenge", force_challenge))
    app.add_handler(CommandHandler("addscore", add_score))
    app.add_handler(MessageHandler(filters.ALL, handle_all_messages))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()