import json
import base64
import random
import logging
import os
from datetime import time, datetime, timedelta
from typing import Dict, List, Tuple, Optional

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
INTIMACY_TASKS_FILE = "intimacy_tasks.txt"
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
    "🥳 Мы рядом",
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

def load_stats() -> Dict[str, Dict]:
    if not os.path.exists(STATS_FILE) or os.path.getsize(STATS_FILE) == 0:
        return {}

    with open(STATS_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()

    try:
        if content and not content.startswith('{'):
            content = base64.b64decode(content).decode('utf-8')
        
        stats = json.loads(content)
        
        if not isinstance(stats, dict):
            return {}
        
        # Инициализируем недостающие поля
        for chat_id, user_stats in stats.items():
            if 'love' not in user_stats:
                user_stats['love'] = 0
            if 'lust' not in user_stats:
                user_stats['lust'] = 0
            if 'spent' not in user_stats:
                user_stats['spent'] = 0
            if 'eternal_challenges' not in user_stats:
                user_stats['eternal_challenges'] = []
            
        return stats
    except Exception as e:
        logger.error(f"Ошибка чтения stats: {e}")
        return {}

def save_stats(new_stats: Dict[str, Dict]) -> None:
    existing_data = {}
    if os.path.exists(STATS_FILE) and os.path.getsize(STATS_FILE) > 0:
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content.startswith('{'):
                    content = base64.b64decode(content).decode('utf-8')
                existing_data = json.loads(content)
        except:
            pass
    
    existing_data.update(new_stats)
    
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)

# ========== Глобальные списки ==========
compliments = load_lines(COMPLIMENTS_FILE)
love_tasks = load_tasks(LOVE_TASKS_FILE)
lust_tasks = load_tasks(LUST_TASKS_FILE)
intimacy_tasks = load_tasks(INTIMACY_TASKS_FILE)
rewards = load_rewards(REWARDS_FILE)

# Проверка, что списки не пусты
if not compliments:
    compliments = ["Ты прекрасна!"]
if not love_tasks:
    love_tasks = [("Скажи, что любишь меня.", 1)]
if not lust_tasks:
    lust_tasks = [("Пофлиртуй с кем-то и отправь пруфы.", 1)]
if not intimacy_tasks:
    intimacy_tasks = [("Обними меня.", 1)]
if not rewards:
    rewards = [("Нет доступных наград", 1)]

# ========== Клавиатура главного меню ==========
main_menu_keyboard = ReplyKeyboardMarkup(
    [
        ["📊 Статистика"],
        ["🥺 Хочу комплимент"],
        ["❤️ Хочу побыть любимой"],
        ["❤️‍🔥 Хочу побыть шлюхой"],
        ["🥳 Мы рядом"],
        ["🛍 Магазин"],
    ],
    resize_keyboard=True,
)

# ========== Функция проверки доступа ==========
async def deny_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id not in ALLOWED_IDS:
        if update.message:
            await update.message.reply_text("Этот бот не для тебя ;)")
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("Этот бот не для тебя ;)")
        return False
    return True

# ========== Функция пересылки сообщений девушки вам ==========
async def forward_to_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    user = message.from_user
    if user.id != HER_USER_ID:
        return

    if message.text and message.text in MENU_COMMANDS:
        return

    name = user.first_name or "Она"
    prefix = f"📨 От {name}:\n\n"

    try:
        if message.text:
            await context.bot.send_message(chat_id=MY_USER_ID, text=prefix + message.text)
        elif message.photo:
            photo = message.photo[-1]
            caption = message.caption or ""
            await context.bot.send_photo(chat_id=MY_USER_ID, photo=photo.file_id, caption=prefix + caption)
        elif message.video:
            caption = message.caption or ""
            await context.bot.send_video(chat_id=MY_USER_ID, video=message.video.file_id, caption=prefix + caption)
        elif message.audio:
            caption = message.caption or ""
            await context.bot.send_audio(chat_id=MY_USER_ID, audio=message.audio.file_id, caption=prefix + caption)
        elif message.voice:
            await context.bot.send_voice(chat_id=MY_USER_ID, voice=message.voice.file_id, caption=prefix + "Голосовое сообщение")
        elif message.document:
            caption = message.caption or ""
            await context.bot.send_document(chat_id=MY_USER_ID, document=message.document.file_id, caption=prefix + caption)
        elif message.sticker:
            await context.bot.send_sticker(chat_id=MY_USER_ID, sticker=message.sticker.file_id)
            await context.bot.send_message(chat_id=MY_USER_ID, text=prefix + "Стикер")
        elif message.video_note:
            await context.bot.send_video_note(chat_id=MY_USER_ID, video_note=message.video_note.file_id)
            await context.bot.send_message(chat_id=MY_USER_ID, text=prefix + "Видеосообщение (кружок)")
        else:
            await context.bot.send_message(chat_id=MY_USER_ID, text=prefix + f"Отправлен {message.content_type}")
    except Exception as e:
        logger.error(f"Ошибка при пересылке: {e}")

# ========== Обработчик команд ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await deny_access(update, context):
        return
    await update.message.reply_text(
        "Привет, моё солнышко :)️\n"
        "Не забывай выполнять оба типа заданий, хорошо?\n\nВыбери, что ты хочешь сейчас:",
        reply_markup=main_menu_keyboard,
    )

async def next_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await deny_access(update, context):
        return
    logger.info("Команда /next_challenge вызвана")

    challenge_hours = context.bot_data.get('challenge_hours', [])
    if not challenge_hours:
        await update.message.reply_text("❌ Список часов вызовов не инициализирован. Проверьте логи бота.")
        return

    try:
        now = datetime.now(TIMEZONE)
        current_hour = now.hour
        current_minute = now.minute

        next_hour = None
        for hour in challenge_hours:
            if hour > current_hour:
                next_hour = hour
                break
            elif hour == current_hour and current_minute == 0:
                continue

        if next_hour is None:
            next_hour = challenge_hours[0] + 24

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

async def force_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != MY_USER_ID:
        await update.message.reply_text("Эта команда только для создателя.")
        return
    await send_challenge(context)
    await update.message.reply_text("✅ Вызов принудительно отправлен!")

async def add_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    stats = load_stats()
    her_chat_id = str(HER_USER_ID)
    if her_chat_id not in stats:
        stats[her_chat_id] = {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []}
    stats[her_chat_id][score_type] += amount
    save_stats(stats)

    type_name = {'love': 'любви', 'lust': 'похоти'}.get(score_type, score_type)
    reason = ' '.join(context.args[2:]) if len(context.args) > 2 else None

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

    await update.message.reply_text(f"✅ Добавлено +{amount} к очкам {type_name} для девушки.")

# ========== Магазин ==========
async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    items_per_page = 5
    total_pages = (len(rewards) + items_per_page - 1) // items_per_page
    page = max(0, min(page, total_pages - 1))

    start = page * items_per_page
    end = start + items_per_page
    current_items = rewards[start:end]

    text = f"🛍 Магазин (страница {page+1}/{total_pages}):\n\n"
    for idx, (name, cost) in enumerate(current_items, start=start+1):
        text += f"{idx}. {name} — {cost} баллов\n"

    keyboard = []
    for i, (name, cost) in enumerate(current_items):
        actual_index = start + i
        keyboard.append([InlineKeyboardButton(f"✅ {name} ({cost})", callback_data=f"buy_{actual_index}_{cost}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"shop_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Вперёд", callback_data=f"shop_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("❌ Закрыть", callback_data="shop_close")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

# ========== Обработчик всех сообщений ==========
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await forward_to_me(update, context)
    if not await deny_access(update, context):
        return

    if update.message and update.message.text:
        text = update.message.text
        user_id = update.effective_user.id
        chat_id = str(update.effective_chat.id)

        if text == "📊 Статистика":
            stats = load_stats()
            user_stats = stats.get(chat_id, {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []})
            current_balance = min(user_stats['love'], user_stats['lust']) - user_stats.get('spent', 0)
            await update.message.reply_text(
                f"📊 Твоя статистика:\n"
                f"Текущий баланс: {current_balance}\n\n"
                f"(Любовь: {user_stats['love']}, Похоть: {user_stats['lust']})",
                reply_markup=main_menu_keyboard,
            )
            if user_id == HER_USER_ID:
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"📊 Она запросила статистику:\n"
                         f"Текущий баланс: {current_balance}\n"
                         f"Любовь: {user_stats['love']}, Похоть: {user_stats['lust']}"
                )

        elif text == "🥺 Хочу комплимент":
            compliment = random.choice(compliments)
            await update.message.reply_text(compliment, reply_markup=main_menu_keyboard)
            if user_id == HER_USER_ID:
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"💬 Она получила комплимент:\n\n{compliment}"
                )

        elif text == "❤️ Хочу побыть любимой":
            task_text, price = random.choice(love_tasks)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Сделала это", callback_data=f"love_done_{price}"),
                 InlineKeyboardButton("❌ Не хочу", callback_data="love_cancel")]
            ])
            await update.message.reply_text(task_text, reply_markup=keyboard)

        elif text == "❤️‍🔥 Хочу побыть шлюхой":
            task_text, price = random.choice(lust_tasks)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Сделала это", callback_data=f"lust_done_{price}"),
                 InlineKeyboardButton("❌ Не хочу", callback_data="lust_cancel")]
            ])
            await update.message.reply_text(task_text, reply_markup=keyboard)

        elif text == "🥳 Мы рядом":
            task_text, price = random.choice(intimacy_tasks)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Сделала это", callback_data=f"intimacy_done_{price}"),
                 InlineKeyboardButton("❌ Не хочу", callback_data="intimacy_cancel")]
            ])
            await update.message.reply_text(task_text, reply_markup=keyboard)

        elif text == "🛍 Магазин":
            await show_shop(update, context, page=0)

# ========== Отправка вызова по расписанию ==========
async def send_challenge(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = HER_USER_ID
    bot_data = context.bot_data
    stats = load_stats()
    her_chat_id = str(HER_USER_ID)
    her_stats = stats.get(her_chat_id, {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []})

    # Удаляем предыдущий активный (обычный) вызов, если есть
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

    # Выбираем случайный тип задания (только love или lust)
    task_type = random.choice(['love', 'lust'])
    if task_type == 'love':
        task_text, price = random.choice(love_tasks)
    else:
        task_text, price = random.choice(lust_tasks)

    # Клавиатура: три кнопки в два ряда: первый ряд - две кнопки, второй - одна
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Выполнила", callback_data=f"challenge_{task_type}_done_{price}"),
            InlineKeyboardButton("❌ Пропустить", callback_data="challenge_skip")
        ],
        [
            InlineKeyboardButton("⭐️ Считай уже сделано, выполню как смогу!", callback_data=f"challenge_eternal_{task_type}_{price}")
        ]
    ])

    message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⚡️ ВЫЗОВ ⚡️\n\n{task_text}\n\nЭто вызов с ограниченным временем, награда x3!\n\nЕсли ты его выполнишь, получишь +{price*3} к {task_type}!\nЕсли справишься лучше чем нужно, я докину баллов за старания!\n\nНе забывай, что у тебя всего 3 часа, чтобы выполнить его, хорошо?",
        reply_markup=keyboard
    )

    # Сохраняем информацию о вызове в bot_data (обычный активный)
    bot_data['challenge_message_id'] = message.message_id
    bot_data['challenge_chat_id'] = chat_id
    bot_data['challenge_task_text'] = task_text
    bot_data['challenge_price'] = price
    bot_data['challenge_type'] = task_type

    # Уведомляем вас
    await context.bot.send_message(
        chat_id=MY_USER_ID,
        text=f"⚡️ Новый вызов для неё:\n\n{task_text} (тип: {task_type}, базовые очки: {price})"
    )

# ========== Обработчик инлайн-кнопок ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await deny_access(update, context):
        if update.callback_query:
            await update.callback_query.answer()
        return

    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id
    chat_id = str(update.effective_chat.id)
    message = query.message

    # --- Обычные задания (любовь/похоть/интимность) ---
    if data.startswith("love_done_"):
        try:
            price = int(data.split("_")[2])
        except (IndexError, ValueError):
            price = 1
        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []}
        stats[chat_id]["love"] += price
        save_stats(stats)
        await message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к любви, сделав это:\n\n{message.text}",
            reply_markup=main_menu_keyboard
        )
        if user_id == HER_USER_ID:
            await context.bot.send_message(chat_id=MY_USER_ID, text=f"✅ Она выполнила задание «{message.text}» и получила +{price} к любви.")
        return

    elif data.startswith("lust_done_"):
        try:
            price = int(data.split("_")[2])
        except (IndexError, ValueError):
            price = 1
        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []}
        stats[chat_id]["lust"] += price
        save_stats(stats)
        await message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к похоти, сделав это:\n\n{message.text}",
            reply_markup=main_menu_keyboard
        )
        if user_id == HER_USER_ID:
            await context.bot.send_message(chat_id=MY_USER_ID, text=f"🔥 Она выполнила задание «{message.text}» и получила +{price} к похоти.")
        return

    elif data.startswith("intimacy_done_"):
        try:
            price = int(data.split("_")[2])
        except (IndexError, ValueError):
            price = 1
        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []}
        stats[chat_id]["love"] += price
        save_stats(stats)
        await message.delete()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Молодец! Ты получила {price} к любви за нежность, сделав это:\n\n{message.text}",
            reply_markup=main_menu_keyboard
        )
        if user_id == HER_USER_ID:
            await context.bot.send_message(chat_id=MY_USER_ID, text=f"🥳 Она выполнила задание «рядом»: «{message.text}» и получила +{price} к любви.")
        return

    elif data in ("love_cancel", "lust_cancel", "intimacy_cancel"):
        await message.delete()
        if user_id == HER_USER_ID:
            task_type_map = {"love_cancel": "любви", "lust_cancel": "похоти", "intimacy_cancel": "нежности"}
            task_type = task_type_map.get(data, "задания")
            await context.bot.send_message(chat_id=MY_USER_ID, text=f"❌ Она отказалась делать задание «{message.text}» (тип: {task_type}).")
        return

    # --- Вызовы ---
    if data.startswith("challenge_"):
        # Разбираем callback_data
        parts = data.split('_')
        # Возможные варианты:
        # challenge_love_done_2, challenge_lust_done_2, challenge_skip, challenge_eternal_love_2, challenge_eternal_lust_2
        if len(parts) >= 4 and parts[1] in ('love', 'lust') and parts[2] == 'done':
            # Обычное выполнение вызова
            challenge_type = parts[1]
            try:
                price = int(parts[3])
            except ValueError:
                price = 1

            # Проверяем, не вечный ли это вызов? Для вечных у нас будет отдельный обработчик ниже
            # Здесь обрабатываем только "done"
            # Проверим, есть ли это сообщение в eternal_challenges
            stats = load_stats()
            her_chat_id = str(HER_USER_ID)
            her_stats = stats.get(her_chat_id, {"eternal_challenges": []})
            eternal_ids = [ch['message_id'] for ch in her_stats.get('eternal_challenges', []) if ch['chat_id'] == chat_id]
            if message.message_id in eternal_ids:
                # Это вечный вызов – удалим из eternal и выполним
                # Находим его в списке
                for ch in her_stats['eternal_challenges']:
                    if ch['message_id'] == message.message_id:
                        # Удаляем из списка
                        her_stats['eternal_challenges'].remove(ch)
                        break
                stats[her_chat_id] = her_stats
                save_stats(stats)
                # Дальше стандартная обработка выполнения
                tripled_price = price * 3
                if chat_id not in stats:
                    stats[chat_id] = {"love": 0, "lust": 0, "spent": 0}
                stats[chat_id][challenge_type] += tripled_price
                save_stats(stats)
                await message.delete()
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚡️ВЫЗОВ ВСЁ⚡️ Ты выполнила вызов и получила x3 баллов: +{tripled_price} к {challenge_type}!",
                    reply_markup=main_menu_keyboard
                )
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"⚡️ Она выполнила вечный вызов: «{message.text}» и получила +{tripled_price} к очкам {challenge_type} (x3 от {price})."
                )
                return

            # Если не вечный, проверяем bot_data
            if 'challenge_message_id' not in context.bot_data or context.bot_data['challenge_message_id'] != message.message_id:
                await message.delete()
                await query.answer("Этот вызов уже недействителен.", show_alert=True)
                return

            # Обычное выполнение
            tripled_price = price * 3
            type_name = {'love': 'любви', 'lust': 'похоти'}.get(challenge_type, challenge_type)

            stats = load_stats()
            if chat_id not in stats:
                stats[chat_id] = {"love": 0, "lust": 0, "spent": 0}
            stats[chat_id][challenge_type] += tripled_price
            save_stats(stats)

            await message.delete()
            for key in ['challenge_message_id', 'challenge_chat_id', 'challenge_task_text', 'challenge_price', 'challenge_type']:
                context.bot_data.pop(key, None)

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚡️ВЫЗОВ ВСЁ⚡️ Ты выполнила вызов и получила x3 баллов: +{tripled_price} к {type_name}!",
                reply_markup=main_menu_keyboard
            )
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"⚡️ Она выполнила вызов: «{context.bot_data.get('challenge_task_text', message.text)}» и получила +{tripled_price} к очкам {type_name} (x3 от {price})."
            )
            return

        elif data == "challenge_skip":
            # Пропуск вызова
            # Проверяем, не вечный ли это?
            stats = load_stats()
            her_chat_id = str(HER_USER_ID)
            her_stats = stats.get(her_chat_id, {"eternal_challenges": []})
            eternal_ids = [ch['message_id'] for ch in her_stats.get('eternal_challenges', []) if ch['chat_id'] == chat_id]
            if message.message_id in eternal_ids:
                # Удаляем из eternal
                for ch in her_stats['eternal_challenges']:
                    if ch['message_id'] == message.message_id:
                        her_stats['eternal_challenges'].remove(ch)
                        break
                stats[her_chat_id] = her_stats
                save_stats(stats)
                await message.delete()
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"❌ Она пропустила вечный вызов: «{message.text}»."
                )
                return

            # Обычный пропуск
            if 'challenge_message_id' not in context.bot_data or context.bot_data['challenge_message_id'] != message.message_id:
                await message.delete()
                await query.answer("Этот вызов уже недействителен.", show_alert=True)
                return

            challenge_task_text = context.bot_data.get('challenge_task_text', 'Неизвестное задание')
            await message.delete()
            for key in ['challenge_message_id', 'challenge_chat_id', 'challenge_task_text']:
                context.bot_data.pop(key, None)
            await context.bot.send_message(
                chat_id=MY_USER_ID,
                text=f"❌ Она пропустила вызов: «{challenge_task_text}»."
            )
            return

        elif data.startswith("challenge_eternal_"):
            # Нажата кнопка "считай уже сделано"
            # Формат: challenge_eternal_love_2 или challenge_eternal_lust_2
            parts = data.split('_')
            if len(parts) >= 4:
                challenge_type = parts[2]  # love или lust
                try:
                    price = int(parts[3])
                except ValueError:
                    price = 1
            else:
                await query.answer("Ошибка данных.", show_alert=True)
                return

            # Получаем текст задания из bot_data или из сообщения
            task_text = context.bot_data.get('challenge_task_text', message.text)

            # Сохраняем в eternal_challenges
            stats = load_stats()
            her_chat_id = str(HER_USER_ID)
            if her_chat_id not in stats:
                stats[her_chat_id] = {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []}
            her_stats = stats[her_chat_id]

            # Добавляем информацию о вечном вызове
            eternal_info = {
                "message_id": message.message_id,
                "chat_id": chat_id,
                "task_text": task_text,
                "task_type": challenge_type,
                "price": price
            }
            if 'eternal_challenges' not in her_stats:
                her_stats['eternal_challenges'] = []
            her_stats['eternal_challenges'].append(eternal_info)
            stats[her_chat_id] = her_stats
            save_stats(stats)

            # Удаляем из bot_data, чтобы при следующем вызове не пытались удалить это сообщение
            if 'challenge_message_id' in context.bot_data and context.bot_data['challenge_message_id'] == message.message_id:
                for key in ['challenge_message_id', 'challenge_chat_id', 'challenge_task_text', 'challenge_price', 'challenge_type']:
                    context.bot_data.pop(key, None)

            # Меняем текст сообщения и клавиатуру
            new_text = f"⚡️ ВЕЧНЫЙ ВЫЗОВ ⚡️\n\n{task_text}\n\nЭто задание теперь всегда с тобой, выполни когда сможешь. Награда x3!"
            new_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Выполнила", callback_data=f"challenge_{challenge_type}_done_{price}"),
                    InlineKeyboardButton("❌ Пропустить", callback_data="challenge_skip")
                ]
            ])
            await query.edit_message_text(text=new_text, reply_markup=new_keyboard)
            await query.answer("Вызов стал вечным!")
            return

    # --- Магазин ---
    if data.startswith("buy_"):
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

        stats = load_stats()
        if chat_id not in stats:
            stats[chat_id] = {"love": 0, "lust": 0, "spent": 0, "eternal_challenges": []}
        user_stats = stats[chat_id]

        current_balance = min(user_stats['love'], user_stats['lust']) - user_stats.get('spent', 0)

        if current_balance < cost:
            await query.answer("❌ Недостаточно баллов! Подкопи их, выполняя задания, хорошо?", show_alert=True)
            if user_id == HER_USER_ID:
                await context.bot.send_message(
                    chat_id=MY_USER_ID,
                    text=f"❌ Она пыталась купить «{reward_name}» за {cost} баллов, но у неё недостаточно (баланс {current_balance})."
                )
            return

        stats[chat_id]['spent'] = stats[chat_id].get('spent', 0) + cost
        save_stats(stats)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 Ты купила награду: «{reward_name}» за {cost} баллов!",
            reply_markup=main_menu_keyboard
        )

        new_balance = min(user_stats['love'], user_stats['lust']) - stats[chat_id]['spent']
        await context.bot.send_message(
            chat_id=MY_USER_ID,
            text=f"✅ Она купила награду: «{reward_name}» за {cost} баллов. Текущий баланс: {new_balance}"
        )

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

    # Генерируем список часов вызовов для команды next_challenge
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