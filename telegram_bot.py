import os
import json
import logging
import csv
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
WEBAPP_URL = 'https://gosod.github.io/tabel_shushary_botWEB/app.html'

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
        if default is None:
            default = []
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {e}")
        return default

    @staticmethod
    def save_json(filename, data):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения {filename}: {e}")

    @staticmethod
    def get_projects():
        default = [
            {"abbr": "РС", "full": "Разработка сайта"},
            {"abbr": "МРК", "full": "Маркетинг"},
            {"abbr": "КП", "full": "Клиентская поддержка"}
        ]
        projects = DataManager.load_json(PROJECTS_FILE, default)
        if not projects:
            DataManager.save_json(PROJECTS_FILE, default)
            return default
        return projects

    @staticmethod
    def get_user_projects(user_id):
        user_projects = DataManager.load_json(USER_PROJECTS_FILE, {})
        all_projects = DataManager.get_projects()
        if str(user_id) not in user_projects:
            return all_projects
        abbrs = user_projects[str(user_id)]
        filtered = [p for p in all_projects if p['abbr'] in abbrs]
        return filtered if filtered else all_projects

    @staticmethod
    def set_user_projects(user_id, abbrs):
        user_projects = DataManager.load_json(USER_PROJECTS_FILE, {})
        user_projects[str(user_id)] = abbrs
        DataManager.save_json(USER_PROJECTS_FILE, user_projects)

    @staticmethod
    def add_project(abbr, full_name):
        projects = DataManager.get_projects()
        for p in projects:
            if p['abbr'] == abbr or p['full'] == full_name:
                return False, "Проект уже существует"
        projects.append({"abbr": abbr, "full": full_name})
        DataManager.save_json(PROJECTS_FILE, projects)
        return True, "Проект добавлен"

    @staticmethod
    def remove_project(abbr):
        projects = DataManager.get_projects()
        for i, p in enumerate(projects):
            if p['abbr'] == abbr:
                projects.pop(i)
                DataManager.save_json(PROJECTS_FILE, projects)
                return True
        return False

    @staticmethod
    def add_report(user_id, username, project, hours, comments):
        reports = DataManager.load_json(REPORTS_FILE, [])
        report = {
            'user_id': user_id,
            'username': username,
            'project': project,
            'hours': hours,
            'comments': comments,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        reports.append(report)
        DataManager.save_json(REPORTS_FILE, reports)
        return report

    @staticmethod
    def get_user_reports(user_id, days=None):
        reports = DataManager.load_json(REPORTS_FILE, [])
        result = [r for r in reports if r['user_id'] == user_id]
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            result = [r for r in result if r.get('date', '') >= cutoff]
        return result

    @staticmethod
    def get_all_reports(days=None):
        reports = DataManager.load_json(REPORTS_FILE, [])
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            reports = [r for r in reports if r.get('date', '') >= cutoff]
        return reports

    @staticmethod
    def get_all_users():
        return DataManager.load_json(USERS_FILE, {})

    @staticmethod
    def register_user(user_id, username):
        users = DataManager.load_json(USERS_FILE, {})
        changed = False
        if str(user_id) not in users:
            users[str(user_id)] = {
                'username': username,
                'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            changed = True
        elif users[str(user_id)].get('username') != username:
            users[str(user_id)]['username'] = username
            changed = True
        if changed:
            DataManager.save_json(USERS_FILE, users)

    @staticmethod
    def delete_user_reports(user_id):
        reports = DataManager.load_json(REPORTS_FILE, [])
        initial = len(reports)
        reports = [r for r in reports if r['user_id'] != user_id]
        DataManager.save_json(REPORTS_FILE, reports)
        return initial - len(reports)

    @staticmethod
    def build_webapp_payload(user_id):
        """Собрать данные для передачи в Web App"""
        projects = DataManager.get_user_projects(user_id)
        all_users = DataManager.get_all_users()
        reports = DataManager.get_all_reports()

        # Статистика текущего пользователя
        user_reports = [r for r in reports if r['user_id'] == user_id]
        user_total_hours = sum(r.get('hours', 0) for r in user_reports)
        user_by_project = {}
        for r in user_reports:
            proj = r.get('project', '-')
            user_by_project[proj] = user_by_project.get(proj, 0) + r.get('hours', 0)

        # Полная статистика (только для admin)
        admin_stats = None
        if user_id in ADMIN_IDS:
            employees = {}
            proj_stats = {}
            for r in reports:
                u = r.get('username', '?')
                if u not in employees:
                    employees[u] = {'name': u, 'hours': 0, 'reports': 0, 'projects': {}}
                employees[u]['hours'] += r.get('hours', 0)
                employees[u]['reports'] += 1
                proj = r.get('project', '-')
                employees[u]['projects'][proj] = employees[u]['projects'].get(proj, 0) + r.get('hours', 0)
                proj_stats[proj] = proj_stats.get(proj, 0) + r.get('hours', 0)

            recent = sorted(reports, key=lambda x: x.get('datetime', ''), reverse=True)[:30]
            recent_fmt = []
            for r in recent:
                try:
                    dt = datetime.strptime(r['datetime'], '%Y-%m-%d %H:%M:%S')
                    date_str = dt.strftime('%d.%m.%Y')
                    time_str = dt.strftime('%H:%M')
                except:
                    date_str = r.get('date', '')
                    time_str = ''
                recent_fmt.append({
                    'date': date_str,
                    'time': time_str,
                    'employee': r.get('username', '-'),
                    'project': r.get('project', '-'),
                    'hours': r.get('hours', 0),
                    'comment': r.get('comments', '-')
                })

            admin_stats = {
                'total_hours': sum(r.get('hours', 0) for r in reports),
                'total_reports': len(reports),
                'employees': list(employees.values()),
                'projects': proj_stats,
                'recent_reports': recent_fmt
            }

        return {
            'admin': user_id in ADMIN_IDS,
            'user_id': user_id,
            'username': all_users.get(str(user_id), {}).get('username', ''),
            'projects': projects,
            'all_projects': DataManager.get_projects(),
            'all_users': [
                {'id': int(uid), 'username': udata.get('username', '?')}
                for uid, udata in all_users.items()
            ],
            'user_stats': {
                'total_hours': user_total_hours,
                'total_reports': len(user_reports),
                'by_project': user_by_project
            },
            'admin_stats': admin_stats
        }


# ==================== HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем новый ли пользователь
    users = DataManager.get_all_users()
    is_new = str(user.id) not in users
    
    DataManager.register_user(user.id, user.username or user.first_name)

    # Уведомляем админов о новом пользователе
    if is_new:
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"👤 <b>Новый пользователь</b>\n"
                         f"Имя: {user.first_name}\n"
                         f"Username: @{user.username or '-'}\n"
                         f"ID: <code>{user.id}</code>",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Уведомление админу {admin_id}: {e}")

    # Передаём данные для Web App
    user_projects = DataManager.get_user_projects(user.id)
    all_projects = DataManager.get_projects()
    all_users = DataManager.get_all_users()
    
    # Статистика пользователя
    user_reports = [r for r in DataManager.get_all_reports() if r.get('user_id') == user.id]
    user_total_hours = sum(r.get('hours', 0) for r in user_reports)
    user_by_project = {}
    for r in user_reports:
        proj = r.get('project', 'Unknown')
        user_by_project[proj] = user_by_project.get(proj, 0) + r.get('hours', 0)
    
    # Админ-статистика
    admin_stats = None
    if user.id in ADMIN_IDS:
        all_reports = DataManager.get_all_reports()
        employees = {}
        proj_stats = {}
        
        for r in all_reports:
            uid = r.get('user_id')
            uname = r.get('username', '?')
            proj = r.get('project', 'Unknown')
            hours = r.get('hours', 0)
            
            if uid not in employees:
                employees[uid] = {'username': uname, 'hours': 0, 'reports': 0, 'projects': {}}
            employees[uid]['hours'] += hours
            employees[uid]['reports'] += 1
            employees[uid]['projects'][proj] = employees[uid]['projects'].get(proj, 0) + hours
            
            proj_stats[proj] = proj_stats.get(proj, 0) + hours
        
        recent = sorted(all_reports, key=lambda x: x.get('datetime', ''), reverse=True)[:30]
        recent_fmt = [{
            'username': r.get('username', '?'),
            'project': r.get('project', '?'),
            'hours': r.get('hours', 0),
            'date': r.get('date', '?'),
            'comments': r.get('comments', '-')
        } for r in recent]
        
        admin_stats = {
            'total_hours': sum(r.get('hours', 0) for r in all_reports),
            'total_reports': len(all_reports),
            'employees': list(employees.values()),
            'projects': proj_stats,
            'recent_reports': recent_fmt
        }
    
    payload = {
        'user_id': user.id,
        'admin': user.id in ADMIN_IDS,
        'username': user.username or user.first_name,
        'projects': user_projects[:20],  # Только первые 20 проектов
        'user_stats': {
            'total_hours': user_total_hours,
            'total_reports': len(user_reports),
            'by_project': dict(list(user_by_project.items())[:10])  # Только топ-10 проектов
        }
    }
    minimal_payload = {'user_id': payload.get('user_id', 0)}
    encoded = urllib.parse.quote(json.dumps(minimal_payload, ensure_ascii=False))
    # v= параметр ломает кэш Telegram при каждом /start
    import time
    cache_bust = int(time.time())
    url = f"{WEBAPP_URL}?v={cache_bust}&data={encoded}"
    logger.info(f"WebApp URL length: {len(url)}, user_id: {minimal_payload.get('user_id')}")

    keyboard = [[KeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(url=url))]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    welcome = f"👋 Привет, {user.first_name}!"
    if is_new:
        welcome += "\n\n🎉 Добро пожаловать! Ты зарегистрирован."
    welcome += "\n\nНажми кнопку чтобы открыть приложение 👇"

    await update.message.reply_text(welcome, reply_markup=reply_markup, parse_mode='HTML')


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        action = data.get('type')

        if action == 'report':
            items = data.get('projects', [{'project': data.get('project'), 'hours': data.get('hours')}])
            general_comment = data.get('comments', '-')

            # Сохраняем каждый проект с его комментарием
            saved = []
            for i in items:
                proj_comment = i.get('comment', '').strip()
                final_comment = proj_comment if proj_comment else general_comment
                report = DataManager.add_report(
                    user.id, user.username or user.first_name,
                    i['project'], i['hours'], final_comment
                )
                saved.append(report)

            total = sum(i.get('hours', 0) for i in items)

            # Строки с комментариями к каждому проекту
            proj_lines_parts = []
            for i in items:
                line = f"  • {i['project']}: {i['hours']} ч"
                c = i.get('comment', '').strip()
                if c:
                    line += f"\n    💬 {c}"
                proj_lines_parts.append(line)
            proj_lines = "\n".join(proj_lines_parts)

            reply = (f"✅ <b>Отчёт сохранён!</b>\n\n"
                     f"📊 <b>Проекты:</b>\n{proj_lines}\n\n"
                     f"⏱ <b>Итого:</b> {total} ч\n"
                     f"📅 {saved[0]['date']}")
            if general_comment and general_comment != '-':
                reply += f"\n💬 {general_comment}"

            await update.message.reply_text(reply, parse_mode='HTML')

            # Уведомление админам
            for admin_id in ADMIN_IDS:
                if admin_id != user.id:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"📬 <b>Новый отчёт</b>\n"
                                 f"👤 {user.first_name} (@{user.username or '-'})\n\n"
                                 f"{proj_lines}\n"
                                 f"⏱ Итого: {total} ч",
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Уведомление админу {admin_id}: {e}")

            # Pending actions — удаления проектов и назначения без закрытия приложения
            for pending in data.get('pending', []):
                p_type = pending.get('type')
                if p_type == 'remove_project' and is_admin(user.id):
                    DataManager.remove_project(pending.get('abbr', ''))
                elif p_type == 'assign_projects' and is_admin(user.id):
                    DataManager.set_user_projects(pending.get('user_id'), pending.get('abbrs', []))

        elif action == 'add_project':
            if not is_admin(user.id):
                return
            ok, msg = DataManager.add_project(data.get('abbr', '').upper(), data.get('full', ''))
            await update.message.reply_text(
                f"✅ <b>{data['abbr']}</b> — {data['full']} добавлен!" if ok else f"❌ {msg}",
                parse_mode='HTML'
            )

        elif action == 'remove_project':
            if not is_admin(user.id):
                return
            ok = DataManager.remove_project(data.get('abbr', ''))
            await update.message.reply_text(
                f"✅ Проект удалён." if ok else "❌ Проект не найден."
            )

        elif action == 'assign_projects':
            if not is_admin(user.id):
                return
            DataManager.set_user_projects(data['user_id'], data.get('abbrs', []))
            await update.message.reply_text(
                f"✅ Проекты назначены для <b>{data.get('username', '')}</b>",
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Ошибка Web App: {e}")
        await update.message.reply_text("❌ Ошибка. Попробуй ещё раз.")


async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ Только для администратора.")
        return

    reports = DataManager.get_all_reports()
    if not reports:
        await update.message.reply_text("📭 Нет данных.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Дата', 'Сотрудник', 'Проект', 'Часы', 'Комментарий'])
    for r in sorted(reports, key=lambda x: x.get('date', '')):
        writer.writerow([r.get('date'), r.get('username'), r.get('project'),
                         r.get('hours'), r.get('comments')])
    output.seek(0)

    await update.message.reply_document(
        document=output.getvalue().encode('utf-8-sig'),
        filename=f"reports_{datetime.now().strftime('%Y%m%d')}.csv",
        caption=f"📊 Экспорт | {len(reports)} отчётов"
    )


async def manual_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ Только для администратора.")
        return
    users = DataManager.get_all_users()
    sent = 0
    for uid_str in users:
        try:
            await context.bot.send_message(
                chat_id=int(uid_str),
                text="📢 <b>Напоминание!</b>\n\nПожалуйста, заполните отчёт за сегодня 👇",
                parse_mode='HTML'
            )
            sent += 1
        except:
            pass
    await update.message.reply_text(f"✅ Отправлено {sent} пользователям.")


def load_schedule():
    """Загружает расписание рабочих дней"""
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки расписания: {e}")
    return None

def is_working_day_for_user(today_iso, user_data, schedule_data):
    """Проверяет является ли сегодня рабочим днём для сотрудника"""
    if schedule_data is None:
        # Fallback: только пн-пт
        d = datetime.strptime(today_iso, '%Y-%m-%d')
        return d.weekday() < 5

    user_schedule = user_data.get('schedule', '5/2')
    schedules = schedule_data.get('schedules', {})

    if user_schedule not in schedules:
        # Неизвестный тип — используем 5/2
        user_schedule = '5/2'

    working_days = schedules[user_schedule].get('working_days', [])
    return today_iso in working_days

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет напоминания сотрудникам у которых нет отчёта за сегодня"""
    msk = pytz.timezone('Europe/Moscow')
    today = datetime.now(msk).strftime('%Y-%m-%d')
    hour  = datetime.now(msk).hour

    users    = DataManager.get_all_users()
    reports  = DataManager.get_all_reports()
    reported = {r['user_id'] for r in reports if r.get('date') == today}
    schedule = load_schedule()

    # Текст зависит от времени: первое или второе напоминание
    if hour >= 20:
        text = (
            "🔔 <b>Последнее напоминание!</b>\n\n"
            "Рабочий день заканчивается — не забудьте внести отчёт 👇"
        )
    else:
        text = (
            "⏰ <b>Напоминание!</b>\n\n"
            "Не забудьте заполнить отчёт за сегодня 👇"
        )

    sent = skipped = 0
    for uid_str, udata in users.items():
        try:
            uid = int(uid_str)

            # Проверяем рабочий ли день по графику сотрудника
            if not is_working_day_for_user(today, udata, schedule):
                skipped += 1
                logger.info(f"Пропускаем {udata.get('username','?')} — выходной по графику {udata.get('schedule','5/2')}")
                continue

            # Уже сдал отчёт — не беспокоим
            if uid in reported:
                skipped += 1
                continue

            await context.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode='HTML'
            )
            sent += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить напоминание {uid_str}: {e}")

    logger.info(f"Напоминания отправлены: {sent}, пропущено: {skipped}")


# ==================== MAIN ====================

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('export', export_csv))
    app.add_handler(CommandHandler('notify', manual_notify))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    moscow_tz = pytz.timezone('Europe/Moscow')
    # Первое напоминание — 18:00 МСК
    app.job_queue.run_daily(
        send_reminder,
        time=time(hour=REMINDER_1_HOUR, minute=0, tzinfo=moscow_tz)
    )
    # Второе напоминание — 20:00 МСК
    app.job_queue.run_daily(
        send_reminder,
        time=time(hour=REMINDER_2_HOUR, minute=0, tzinfo=moscow_tz)
    )

    logger.info("🤖 Бот запущен!")
    logger.info(f"📱 Web App: {WEBAPP_URL}")
    logger.info(f"⏰ Напоминания: {REMINDER_1_HOUR}:00 и {REMINDER_2_HOUR}:00 МСК")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
