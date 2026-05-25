import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import logging

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8699806791:AAGlHkGhcm62SkyPs-EansNAlgPlqLi22M4  # Замените на токен вашего бота
ADMIN_ID = 8578587779  # Замените на ваш Telegram ID

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ========== СОЗДАНИЕ БАЗЫ ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_date TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_text TEXT,
            created_by INTEGER,
            created_at TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS completed_tasks (
            user_id INTEGER,
            task_id INTEGER,
            completed_at TEXT,
            PRIMARY KEY (user_id, task_id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ========== FSM СОСТОЯНИЯ ==========
class AdminStates(StatesGroup):
    waiting_for_task_text = State()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def add_user(user_id, username, first_name):
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM users')
    users = cur.fetchall()
    conn.close()
    return [u[0] for u in users]

def save_task(task_text, admin_id):
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO tasks (task_text, created_by, created_at)
        VALUES (?, ?, ?)
    ''', (task_text, admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id

def get_active_tasks():
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT id, task_text FROM tasks WHERE is_active = 1')
    tasks = cur.fetchall()
    conn.close()
    return tasks

def mark_task_completed(user_id, task_id):
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT OR IGNORE INTO completed_tasks (user_id, task_id, completed_at)
        VALUES (?, ?, ?)
    ''', (user_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def is_task_completed(user_id, task_id):
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM completed_tasks WHERE user_id = ? AND task_id = ?', (user_id, task_id))
    result = cur.fetchone()
    conn.close()
    return result is not None

def get_user_completed_tasks_count(user_id):
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM completed_tasks WHERE user_id = ?', (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def deactivate_task(task_id):
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE tasks SET is_active = 0 WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

def get_all_users_with_stats():
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT u.user_id, u.username, u.first_name, u.joined_date,
               COUNT(c.task_id) as completed_count
        FROM users u
        LEFT JOIN completed_tasks c ON u.user_id = c.user_id
        GROUP BY u.user_id
        ORDER BY completed_count DESC
    ''')
    users = cur.fetchall()
    conn.close()
    return users

# ========== ИНЛАЙН-КЛАВИАТУРЫ ==========

# Главная клавиатура (для всех пользователей)
def get_main_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 МОИ ЗАДАНИЯ", callback_data="my_tasks")],
        [InlineKeyboardButton(text="✅ ВЫПОЛНЕННЫЕ", callback_data="completed_tasks")],
        [InlineKeyboardButton(text="📊 МОЯ СТАТИСТИКА", callback_data="my_stats")]
    ])
    
    # Кнопка админ-панели только для админа
    if user_id == ADMIN_ID:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_panel")]
        )
    
    return keyboard

# Админ-панель
def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ НОВОЕ ЗАДАНИЕ", callback_data="admin_new_task")],
        [InlineKeyboardButton(text="🗑 УПРАВЛЕНИЕ ЗАДАНИЯМИ", callback_data="admin_manage_tasks")],
        [InlineKeyboardButton(text="👥 ВСЕ ПОЛЬЗОВАТЕЛИ", callback_data="admin_users")],
        [InlineKeyboardButton(text="📈 ОБЩАЯ СТАТИСТИКА", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ])

# Клавиатура со списком заданий
def get_tasks_list_keyboard(tasks, user_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for task_id, task_text in tasks:
        # Проверяем, выполнено ли задание
        completed = is_task_completed(user_id, task_id)
        status_emoji = "✅" if completed else "📌"
        
        # Сокращаем текст кнопки
        short_text = task_text[:35] + "..." if len(task_text) > 35 else task_text
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{status_emoji} {short_text}", 
                callback_data=f"view_task_{task_id}"
            )
        ])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    return keyboard

# Клавиатура для конкретного задания
def get_task_action_keyboard(task_id, user_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if not is_task_completed(user_id, task_id):
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="✅ ВЫПОЛНИТЬ ЗАДАНИЕ", callback_data=f"complete_task_{task_id}")
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ К СПИСКУ ЗАДАНИЙ", callback_data="my_tasks"),
        InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")
    ])
    
    return keyboard

# Клавиатура управления заданиями (для админа)
def get_admin_manage_keyboard():
    tasks = get_active_tasks()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if tasks:
        for task_id, task_text in tasks:
            short_text = task_text[:30] + "..." if len(task_text) > 30 else task_text
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"❌ {short_text}", 
                    callback_data=f"admin_delete_task_{task_id}"
                )
            ])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="➕ НОВОЕ ЗАДАНИЕ", callback_data="admin_new_task")])
    else:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="➕ СОЗДАТЬ ПЕРВОЕ ЗАДАНИЕ", callback_data="admin_new_task")])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД В АДМИН-ПАНЕЛЬ", callback_data="admin_panel")])
    return keyboard

# Клавиатура для просмотра пользователей (с пагинацией)
def get_users_keyboard(users, page=0, items_per_page=5):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_users = users[start_idx:end_idx]
    
    for user in page_users:
        user_id, username, first_name, joined_date, completed_count = user
        display_name = first_name if first_name else f"ID:{user_id}"
        if username and username != "Нет username":
            display_name = f"@{username}"
        
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"👤 {display_name} | ✅{completed_count}", 
                callback_data=f"admin_view_user_{user_id}"
            )
        ])
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ НАЗАД", callback_data=f"admin_users_page_{page-1}"))
    if end_idx < len(users):
        nav_buttons.append(InlineKeyboardButton(text="ВПЕРЕД ▶️", callback_data=f"admin_users_page_{page+1}"))
    
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД В АДМИН-ПАНЕЛЬ", callback_data="admin_panel")])
    return keyboard

# Клавиатура для просмотра деталей пользователя
def get_user_detail_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К СПИСКУ ПОЛЬЗОВАТЕЛЕЙ", callback_data="admin_users")],
        [InlineKeyboardButton(text="🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ])

# ========== ОБРАБОТЧИКИ ==========

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    first_name = message.from_user.first_name or ""
    
    add_user(user_id, username, first_name)
    
    welcome_text = (
        f"✨ *ДОБРО ПОЖАЛОВАТЬ, {first_name.upper()}!* ✨\n\n"
        f"Я бот для выполнения заданий от администратора.\n\n"
        f"📌 *Используйте кнопки ниже* для:\n"
        f"• Просмотра активных заданий\n"
        f"• Отметки выполненных заданий\n"
        f"• Просмотра вашей статистики\n\n"
        f"👇 *ВЫБЕРИТЕ ДЕЙСТВИЕ:*"
    )
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

# ГЛАВНОЕ МЕНЮ
@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        "🏠 *ГЛАВНОЕ МЕНЮ*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )
    await callback.answer()

# МОИ ЗАДАНИЯ
@dp.callback_query(F.data == "my_tasks")
async def my_tasks(callback: CallbackQuery):
    user_id = callback.from_user.id
    tasks = get_active_tasks()
    
    if not tasks:
        await callback.message.edit_text(
            "📭 *НЕТ АКТИВНЫХ ЗАДАНИЙ*\n\n"
            "Новых заданий пока нет. Загляните позже! 🔔",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
        await callback.answer()
        return
    
    # Формируем текст с заданиями
    text = "📋 *МОИ ЗАДАНИЯ*\n\n"
    for task_id, task_text in tasks:
        completed = is_task_completed(user_id, task_id)
        status = "✅ ВЫПОЛНЕНО" if completed else "⏳ ОЖИДАЕТ"
        text += f"┌ *Задание #{task_id}*\n│ {task_text}\n└ [{status}]\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_tasks_list_keyboard(tasks, user_id)
    )
    await callback.answer()

# ПРОСМОТР КОНКРЕТНОГО ЗАДАНИЯ
@dp.callback_query(F.data.startswith("view_task_"))
async def view_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT task_text, is_active FROM tasks WHERE id = ?', (task_id,))
    result = cur.fetchone()
    conn.close()
    
    if not result or result[1] == 0:
        await callback.answer("❌ Задание больше не доступно", show_alert=True)
        return
    
    task_text = result[0]
    completed = is_task_completed(user_id, task_id)
    
    status_text = "✅ ВЫПОЛНЕНО" if completed else "⏳ НЕ ВЫПОЛНЕНО"
    
    text = (
        f"📌 *ЗАДАНИЕ #{task_id}*\n\n"
        f"📝 {task_text}\n\n"
        f"└ Статус: {status_text}\n\n"
    )
    
    if not completed:
        text += "👇 Нажмите кнопку ниже, чтобы отметить задание как выполненное!"
    else:
        text += "🎉 Отлично! Вы уже выполнили это задание!"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_task_action_keyboard(task_id, user_id)
    )
    await callback.answer()

# ВЫПОЛНИТЬ ЗАДАНИЕ
@dp.callback_query(F.data.startswith("complete_task_"))
async def complete_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if is_task_completed(user_id, task_id):
        await callback.answer("❌ Вы уже выполнили это задание!", show_alert=True)
        return
    
    # Проверяем активность задания
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT is_active, task_text FROM tasks WHERE id = ?', (task_id,))
    result = cur.fetchone()
    conn.close()
    
    if not result or result[0] == 0:
        await callback.answer("❌ Это задание больше не активно", show_alert=True)
        return
    
    # Отмечаем выполненным
    mark_task_completed(user_id, task_id)
    completed_count = get_user_completed_tasks_count(user_id)
    
    # Поздравление
    congratulations = [
        "🎉 ОТЛИЧНО!",
        "🌟 ТЫ СПРАВИЛСЯ!",
        "💪 МОЛОДЕЦ!",
        "🏆 ТЫ ПРОФИ!",
        "✨ ВЕЛИКОЛЕПНО!"
    ]
    import random
    congrats = random.choice(congratulations)
    
    text = (
        f"{congrats}\n\n"
        f"✅ *Задание #{task_id} выполнено!*\n\n"
        f"📊 *Всего выполнено:* {completed_count} заданий\n\n"
        f"Продолжай в том же духе! 🚀"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )
    
    # Уведомление админу
    user_name = callback.from_user.first_name or callback.from_user.username or "Пользователь"
    await bot.send_message(
        ADMIN_ID,
        f"📢 *ПОЛЬЗОВАТЕЛЬ ВЫПОЛНИЛ ЗАДАНИЕ*\n\n"
        f"👤 {user_name}\n"
        f"📌 Задание #{task_id}\n"
        f"📝 {result[1][:100]}\n"
        f"🎯 Всего выполнено: {completed_count}",
        parse_mode="Markdown"
    )
    
    await callback.answer("✅ Задание выполнено!")

# ВЫПОЛНЕННЫЕ ЗАДАНИЯ
@dp.callback_query(F.data == "completed_tasks")
async def completed_tasks(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT t.id, t.task_text, c.completed_at 
        FROM completed_tasks c
        JOIN tasks t ON c.task_id = t.id
        WHERE c.user_id = ?
        ORDER BY c.completed_at DESC
    ''', (user_id,))
    tasks = cur.fetchall()
    conn.close()
    
    if not tasks:
        await callback.message.edit_text(
            "📭 *ВЫПОЛНЕННЫХ ЗАДАНИЙ НЕТ*\n\n"
            "Начните выполнять задания из раздела 📋 МОИ ЗАДАНИЯ!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
        await callback.answer()
        return
    
    text = "✅ *МОИ ВЫПОЛНЕННЫЕ ЗАДАНИЯ*\n\n"
    for task_id, task_text, completed_at in tasks:
        date = completed_at.split()[0] if completed_at else "Неизвестно"
        text += f"📌 *#{task_id}* (выполнено: {date})\n   {task_text[:60]}\n\n"
    
    # Если текста слишком много, обрезаем
    if len(text) > 4000:
        text = text[:3997] + "..."
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )
    await callback.answer()

# МОЯ СТАТИСТИКА
@dp.callback_query(F.data == "my_stats")
async def my_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    completed_count = get_user_completed_tasks_count(user_id)
    active_tasks = len(get_active_tasks())
    
    # Определяем уровень
    if completed_count < 5:
        level = "🌱 НОВИЧОК"
        emoji = "🌱"
        next_goal = 5 - completed_count
    elif completed_count < 15:
        level = "⭐ СТАЖЕР"
        emoji = "⭐"
        next_goal = 15 - completed_count
    elif completed_count < 30:
        level = "🚀 МАСТЕР"
        emoji = "🚀"
        next_goal = 30 - completed_count
    else:
        level = "🏆 ЛЕГЕНДА"
        emoji = "🏆"
        next_goal = 0
    
    text = (
        f"📊 *СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ*\n\n"
        f"{emoji} *Уровень:* {level}\n"
        f"✅ *Выполнено заданий:* {completed_count}\n"
        f"📋 *Активных заданий:* {active_tasks}\n"
    )
    
    if next_goal > 0:
        text += f"🎯 *До следующего уровня:* {next_goal} заданий\n"
    
    # Процент выполнения
    if active_tasks > 0:
        completed_of_active = sum(1 for tid, _ in get_active_tasks() if is_task_completed(user_id, tid))
        percent = int(completed_of_active / active_tasks * 100)
        text += f"\n📊 *Прогресс по текущим заданиям:* {percent}%"
        text += f"\n└ Выполнено {completed_of_active} из {active_tasks}"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )
    await callback.answer()

# ========== АДМИН-ПАНЕЛЬ ==========

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ ДОСТУП ЗАПРЕЩЕН", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚙️ *АДМИН-ПАНЕЛЬ*\n\n"
        "Управление заданиями и пользователями:",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

# НОВОЕ ЗАДАНИЕ
@dp.callback_query(F.data == "admin_new_task")
async def admin_new_task(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ ДОСТУП ЗАПРЕЩЕН", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 *СОЗДАНИЕ НОВОГО ЗАДАНИЯ*\n\n"
        "Введите текст задания:\n\n"
        "✏️ Например:\n"
        "• Пройти опрос по ссылке: https://example.com\n"
        "• Подписаться на канал: @channel\n"
        "• Написать отзыв в группу\n\n"
        "⏸ *Отмена:* /cancel",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_task_text)
    await callback.answer()

@dp.message(AdminStates.waiting_for_task_text)
async def process_new_task(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа")
        return
    
    task_text = message.text
    
    if task_text.lower() == "/cancel":
        await state.clear()
        await message.answer(
            "❌ Создание задания отменено",
            reply_markup=get_admin_keyboard()
        )
        return
    
    task_id = save_task(task_text, ADMIN_ID)
    
    # Рассылка уведомлений
    users = get_all_users()
    success_count = 0
    
    notification = (
        f"🔔🔔🔔 *НОВАЯ ЗАДАЧА ОТ АДМИНА* 🔔🔔🔔\n\n"
        f"📌 *Задание #{task_id}*\n"
        f"📝 {task_text}\n\n"
        f"✨ Нажмите 📋 МОИ ЗАДАНИЯ в главном меню, чтобы выполнить!"
    )
    
    for user_id in users:
        try:
            await bot.send_message(user_id, notification, parse_mode="Markdown")
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Ошибка отправки {user_id}: {e}")
    
    await message.answer(
        f"✅ *ЗАДАНИЕ СОЗДАНО И ОТПРАВЛЕНО!*\n\n"
        f"📌 Задание #{task_id}\n"
        f"📝 {task_text}\n\n"
        f"📊 Отправлено уведомлений: {success_count} из {len(users)}",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )
    
    await state.clear()

# УПРАВЛЕНИЕ ЗАДАНИЯМИ
@dp.callback_query(F.data == "admin_manage_tasks")
async def admin_manage_tasks(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ ДОСТУП ЗАПРЕЩЕН", show_alert=True)
        return
    
    tasks = get_active_tasks()
    
    if not tasks:
        text = "🗑 *УПРАВЛЕНИЕ ЗАДАНИЯМИ*\n\nНет активных заданий для удаления."
    else:
        text = "🗑 *УПРАВЛЕНИЕ ЗАДАНИЯМИ*\n\nНажмите на задание, чтобы удалить его:\n\n"
        for task_id, task_text in tasks:
            text += f"❌ Задание #{task_id}: {task_text[:60]}\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_admin_manage_keyboard()
    )
    await callback.answer()

# УДАЛЕНИЕ ЗАДАНИЯ
@dp.callback_query(F.data.startswith("admin_delete_task_"))
async def admin_delete_task(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ ДОСТУП ЗАПРЕЩЕН", show_alert=True)
        return
    
    task_id = int(callback.data.split("_")[3])
    
    # Получаем текст задания для подтверждения
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT task_text FROM tasks WHERE id = ?', (task_id,))
    task = cur.fetchone()
    conn.close()
    
    if task:
        deactivate_task(task_id)
        await callback.answer(f"✅ Задание #{task_id} удалено!", show_alert=True)
    else:
        await callback.answer("❌ Задание не найдено", show_alert=True)
    
    # Обновляем список
    await admin_manage_tasks(callback)

# ВСЕ ПОЛЬЗОВАТЕЛИ
@dp.callback_query(F.data.startswith("admin_users"))
async def admin_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ ДОСТУП ЗАПРЕЩЕН", show_alert=True)
        return
    
    users = get_all_users_with_stats()
    
    if not users:
        await callback.message.edit_text(
            "👥 *ПОЛЬЗОВАТЕЛИ*\n\nНет зарегистрированных пользователей",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return
    
    # Извлекаем номер страницы
    parts = callback.data.split("_")
    page = int(parts[-1]) if len(parts) > 2 and parts[-1].isdigit() else 0
    
    total_users = len(users)
    start_idx = page * 5
    end_idx = min(start_idx + 5, total_users)
    
    text = f"👥 *СПИСОК ПОЛЬЗОВАТЕЛЕЙ*\n\n"
    text += f"📊 Всего: {total_users} пользователей\n"
    text += f"📄 Страница {page + 1} из {(total_users + 4) // 5}\n\n"
    
    for i in range(start_idx, end_idx):
        user = users[i]
        user_id, username, first_name, joined_date, completed_count = user
        display_name = first_name if first_name else f"Пользователь"
        if username and username != "Нет username":
            display_name = f"@{username}"
        
        text += f"👤 *{display_name}*\n"
        text += f"   ✅ Выполнено: {completed_count}\n"
        text += f"   🆔 ID: {user_id}\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_users_keyboard(users, page)
    )
    await callback.answer()

# ПРОСМОТР ПОЛЬЗОВАТЕЛЯ
@dp.callback_query(F.data.startswith("admin_view_user_"))
async def admin_view_user(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ ДОСТУП ЗАПРЕЩЕН", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[3])
    
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    cur.execute('SELECT username, first_name, joined_date FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()
    
    cur.execute('''
        SELECT t.id, t.task_text, c.completed_at 
        FROM completed_tasks c
        JOIN tasks t ON c.task_id = t.id
        WHERE c.user_id = ?
        ORDER BY c.completed_at DESC
        LIMIT 10
    ''', (user_id,))
    completed_tasks = cur.fetchall()
    conn.close()
    
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    username, first_name, joined_date = user
    display_name = first_name if first_name else f"ID:{user_id}"
    
    text = f"👤 *ДЕТАЛИ ПОЛЬЗОВАТЕЛЯ*\n\n"
    text += f"📛 Имя: {display_name}\n"
    if username and username != "Нет username":
        text += f"🔖 Username: @{username}\n"
    text += f"🆔 ID: {user_id}\n"
    text += f"📅 Дата регистрации: {joined_date.split()[0]}\n"
    text += f"✅ Выполнено заданий: {len(completed_tasks)}\n\n"
    
    if completed_tasks:
        text += f"📋 *Последние задания:*\n"
        for tid, ttext, completed_at in completed_tasks[:5]:
            date = completed_at.split()[0] if completed_at else "?"
            text += f"   • Задание #{tid} ({date})\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_user_detail_keyboard(user_id)
    )
    await callback.answer()

# ОБЩАЯ СТАТИСТИКА
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ ДОСТУП ЗАПРЕЩЕН", show_alert=True)
        return
    
    conn = sqlite3.connect('tasks_bot.db')
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM users')
    total_users = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM tasks')
    total_tasks = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM tasks WHERE is_active = 1')
    active_tasks = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM completed_tasks')
    total_completions = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(DISTINCT user_id) FROM completed_tasks')
    active_users = cur.fetchone()[0]
    
    conn.close()
    
    avg_completions = total_completions / total_users if total_users > 0 else 0
    
    text = (
        f"📈 *ОБЩАЯ СТАТИСТИКА БОТА*\n\n"
        f"👥 *Пользователи:*\n"
        f"   └ Всего: {total_users}\n"
        f"   └ Активных: {active_users}\n\n"
        f"📋 *Задания:*\n"
        f"   └ Всего создано: {total_tasks}\n"
        f"   └ Активных: {active_tasks}\n\n"
        f"✅ *Выполнения:*\n"
        f"   └ Всего: {total_completions}\n"
        f"   └ В среднем на пользователя: {avg_completions:.1f}\n\n"
        f"🎯 *Конверсия:*\n"
        f"   └ Активных: {int(active_users/total_users*100) if total_users > 0 else 0}%"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

# КОМАНДА ОТМЕНЫ
@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет активных действий")
        return
    
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=get_admin_keyboard()
    )

# ========== ЗАПУСК ==========
async def main():
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
