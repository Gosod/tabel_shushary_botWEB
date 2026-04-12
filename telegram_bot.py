 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/telegram_bot.py b/telegram_bot.py
index 1962749688920657725ba9358d6d5d490c9c48fb..67d1cfcd5c7dc27d01124628112eb6e0cce010ff 100644
--- a/telegram_bot.py
+++ b/telegram_bot.py
@@ -5,51 +5,51 @@ import csv
 import io
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
 # Production bot token
 # Set via systemd environment or export before running
 TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
 if not TOKEN:
     raise ValueError("TELEGRAM_BOT_TOKEN environment variable must be set!")
-WEBAPP_URL = 'https://gosod.github.io/tabel_shushary_botWEB/index.html'
+WEBAPP_URL = 'https://gosod.github.io/tabel_shushary_botWEB/'
 
 REPORTS_FILE = 'reports.json'
 USERS_FILE = 'users.json'
 PROJECTS_FILE = 'projects.json'
 USER_PROJECTS_FILE = 'user_projects.json'
 
 # Admin user IDs - UPDATE THESE!
 ADMIN_IDS = [
     699229724,   # mchsman
     924261386,   # eugeneoldyard
 ]
 # Два напоминания — 18:00 и 20:00 МСК
 REMINDER_1_HOUR = 18
 REMINDER_2_HOUR = 20
 SCHEDULE_FILE = 'schedule_2026.json'
 
 
 def is_admin(user_id):
     return user_id in ADMIN_IDS
 
 
 class DataManager:
 
     @staticmethod
     def load_json(filename, default=None):
 
EOF
)
