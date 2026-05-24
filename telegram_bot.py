import os
import json
import logging
import io
import csv
import urllib.parse
from datetime import datetime, time, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import pytz

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === НАСТРОЙКИ ===
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable must be set!")

# Версия бота - увеличивайте при обновлениях
BOT_VERSION = "1.1.0"

WEBAPP_URL = 'https://gosod.github.io/tabel_shushary_botWEB/'

REPORTS_FILE = 'reports.json'
USERS_FILE = 'users.json'
PROJECTS_FILE = 'projects.json'
USER_PROJECTS_FILE = 'user_projects.json'
SCHEDULE_FILE = 'schedule_2026.json'
CACHE_FILE = 'bot_cache.json'

# Admin user IDs
ADMIN_IDS = [
    699229724,   # mchsman
    924261386,   # eugeneoldyard
]

# Напоминания — 18:00 и 20:00 МСК
REMINDER_1_HOUR = 18
REMINDER_2_HOUR = 20


def is_admin(user_id):
    return user_id in ADMIN_IDS


class DataManager:

    @staticmethod
    def load_json(filename, default=None):
        if default is None:
            default = {}
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    @staticmethod
    def save_json(filename, data):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def clear_user_cache(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Очищает кеш конкретного пользователя при запуске бота.
    Сбрасывает состояние диалога и проверяет версию бота.
    Возвращает True, если кеш был очищен, False - если версия актуальна.
    """
    logger.info(f"Проверка кеша для пользователя {user_id}")
    
    # Загружаем кеш пользователя
    cache = DataManager.load_json(CACHE_FILE, {})
    user_cache = cache.get(str(user_id), {})
    stored_version = user_cache.get("version", "0.0.0")
    
    # Если версия устарела - очищаем кеш состояния
    if stored_version != BOT_VERSION:
        logger.info(f"Версия устарела: {stored_version} -> {BOT_VERSION}. Очистка кеша.")
        
        # Сбрасываем состояние диалога (FSM)
        if context.user_data:
            context.user_data.clear()
        
        # Обновляем версию в кеше
        cache[str(user_id)] = {"version": BOT_VERSION, "cleared_at": datetime.now().isoformat()}
        DataManager.save_json(CACHE_FILE, cache)
        
        logger.info(f"Кеш пользователя {user_id} очищен, версия обновлена до {BOT_VERSION}")
        return True
    else:
        logger.info(f"Версия актуальна ({BOT_VERSION}), очистка не требуется")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start.
    Проверяет версию бота и при необходимости очищает кеш пользователя.
    """
    user = update.effective_user
    user_id = user.id
    
    # Проверяем и очищаем кеш при необходимости
    cache_cleared = clear_user_cache(user_id, context)
    
    # Создаём клавиатуру с кнопкой для веб-приложения
    keyboard = [
        [KeyboardButton("📊 Открыть табель", web_app=WebAppInfo(url=WEBAPP_URL))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if cache_cleared:
        welcome_message = (
            f"Привет, {user.first_name}! 👋\n\n"
            f"Обнаружена новая версия бота ({BOT_VERSION}).\n"
            "Ваш кеш очищен — вы видите последнюю версию.\n"
            "Нажмите кнопку ниже, чтобы открыть табель."
        )
        logger.info(f"Команда /start выполнена для пользователя {user_id} (кеш очищен)")
    else:
        welcome_message = (
            f"Привет, {user.first_name}! 👋\n\n"
            f"У вас актуальная версия бота ({BOT_VERSION}).\n"
            "Нажмите кнопку ниже, чтобы открыть табель."
        )
        logger.info(f"Команда /start выполнена для пользователя {user_id} (кеш не требовался)")
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = (
        "🤖 Бот для ведения табеля рабочего времени\n\n"
        "Команды:\n"
        "/start - Запустить бота и очистить кеш\n"
        "/help - Показать эту справку\n\n"
        "Нажмите кнопку в меню, чтобы открыть веб-интерфейс табеля."
    )
    await update.message.reply_text(help_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик обычных сообщений"""
    await update.message.reply_text(
        "Используйте кнопку меню или команду /start для работы с ботом."
    )


async def export_reports(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Экспорт отчётов для администраторов"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    reports = DataManager.load_json(REPORTS_FILE, {})
    
    if not reports:
        await update.message.reply_text("📭 Отчётов пока нет.")
        return
    
    # Создаём CSV файл
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'Date', 'Project', 'Hours', 'Comment'])
    
    for user_id_str, user_reports in reports.items():
        for report in user_reports:
            writer.writerow([
                user_id_str,
                report.get('date', ''),
                report.get('project', ''),
                report.get('hours', ''),
                report.get('comment', '')
            ])
    
    output.seek(0)
    file_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
    file_bytes.name = f'reports_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    await update.message.reply_document(document=file_bytes)
    logger.info(f"Отчёты экспортированы администратором {user_id}")


def main() -> None:
    """Запуск бота"""
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("export", export_reports))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
