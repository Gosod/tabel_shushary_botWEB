#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API v3 для Telegram Time Tracking Bot
+ Управление отчётами (редактирование/удаление)
+ Фиксы дат и часовых поясов
+ Google Sheets интеграция
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
CORS(app)

# Пути к файлам данных
REPORTS_FILE = 'reports.json'
USERS_FILE = 'users.json'
PROJECTS_FILE = 'projects.json'
USER_PROJECTS_FILE = 'user_projects.json'
CREDENTIALS_FILE = 'credentials.json'

# Google Sheets
SPREADSHEET_ID = ''
SHEET_REPORTS = 'Отчёты'

# Админы
ADMIN_IDS = 

# Timezone
MSK = pytz.timezone('Europe/Moscow')


# ==================== HELPERS ====================

def load_json(filepath, default=None):
    if default is None:
        default = []
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки {filepath}: {e}")
    return default


def save_json(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка сохранения {filepath}: {e}")
        return False


def is_admin(user_id):
    return int(user_id) in ADMIN_IDS


def get_msk_now():
    return datetime.now(MSK)


def generate_report_id():
    return datetime.now(MSK).strftime('%Y%m%d%H%M%S%f')


# ==================== GOOGLE SHEETS ====================

def get_sheets_client():
    """Авторизация в Google Sheets через service account"""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds)


def append_to_sheets(report):
    """Добавить строку отчёта в лист 'Отчёты'"""
    try:
        client = get_sheets_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_REPORTS)

        dt_str = report.get('datetime', '')
        try:
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            date_str = dt.strftime('%d.%m.%Y')
            time_str = dt.strftime('%H:%M:%S')
        except:
            date_str = report.get('date', '')
            time_str = ''

        row = [
            date_str,
            time_str,
            report.get('username', ''),
            report.get('project', ''),
            report.get('hours', 0),
            report.get('comments', '')
        ]

        sheet.append_row(row, value_input_option='USER_ENTERED')
        print(f"[Sheets] Добавлена строка: {row}")
        return True
    except Exception as e:
        print(f"[Sheets] Ошибка записи: {e}")
        return False


# ==================== API ENDPOINTS ====================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'version': '3.1',
        'timestamp': get_msk_now().isoformat()
    })


@app.route('/api/init', methods=['POST'])
def init_data():
    data = request.get_json()
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({'error': 'user_id required'}), 400

    all_projects = load_json(PROJECTS_FILE, [])
    all_users = load_json(USERS_FILE, {})
    user_projects_map = load_json(USER_PROJECTS_FILE, {})
    all_reports = load_json(REPORTS_FILE, [])

    user_projects = user_projects_map.get(str(user_id), [])
    if not user_projects:
        user_projects = [p['abbr'] for p in all_projects]

    projects = [p for p in all_projects if p['abbr'] in user_projects]

    user_reports = [r for r in all_reports if r.get('user_id') == user_id]
    user_total_hours = sum(r.get('hours', 0) for r in user_reports)
    user_by_project = {}
    for r in user_reports:
        proj = r.get('project', 'Unknown')
        user_by_project[proj] = user_by_project.get(proj, 0) + r.get('hours', 0)

    response = {
        'admin': is_admin(user_id),
        'user_id': user_id,
        'username': all_users.get(str(user_id), {}).get('username', ''),
        'projects': projects,
        'user_stats': {
            'total_hours': user_total_hours,
            'total_reports': len(user_reports),
            'by_project': user_by_project
        }
    }

    if is_admin(user_id):
        response['all_projects'] = all_projects
        response['all_users'] = [
            {'id': int(uid), 'username': udata.get('username', '?')}
            for uid, udata in all_users.items()
        ]

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

        unique_report_projects = sorted(
            set(r.get('project', '') for r in all_reports if r.get('project')),
            key=lambda x: x.lower()
        )
        response['admin_stats'] = {
            'total_hours': sum(r.get('hours', 0) for r in all_reports),
            'total_reports': len(all_reports),
            'employees': list(employees.values()),
            'projects': proj_stats,
            'recent_reports': recent,
            'unique_report_projects': unique_report_projects
        }

    return jsonify(response)


@app.route('/api/report', methods=['POST'])
def submit_report():
    data = request.get_json()
    user_id = data.get('user_id')
    username = data.get('username', '?')
    projects = data.get('projects', [])
    comments = data.get('comments', '-')

    on_behalf_of_user_id = data.get('on_behalf_of_user_id')
    on_behalf_of_username = data.get('on_behalf_of_username')
    custom_date = data.get('custom_date')

    if on_behalf_of_user_id and is_admin(user_id):
        report_user_id = on_behalf_of_user_id
        report_username = on_behalf_of_username or '?'
    else:
        report_user_id = user_id
        report_username = username

    if not report_user_id or not projects:
        return jsonify({'error': 'user_id and projects required'}), 400

    reports = load_json(REPORTS_FILE, [])

    if custom_date:
        try:
            now = MSK.localize(datetime.strptime(custom_date, '%Y-%m-%d'))
        except Exception:
            now = get_msk_now()
    else:
        now = get_msk_now()

    saved = []
    for item in projects:
        proj_comment = item.get('comment', '').strip()
        final_comment = proj_comment if proj_comment else comments

        report = {
            'id': generate_report_id(),
            'user_id': report_user_id,
            'username': report_username,
            'project': item['project'],
            'hours': item['hours'],
            'comments': final_comment,
            'date': now.strftime('%Y-%m-%d'),
            'datetime': now.strftime('%Y-%m-%d %H:%M:%S')
        }
        reports.append(report)
        saved.append(report)

        # Записываем в Google Sheets
        append_to_sheets(report)

    save_json(REPORTS_FILE, reports)

    return jsonify({'success': True, 'saved': len(saved), 'reports': saved})


@app.route('/api/reports', methods=['GET'])
def get_reports():
    user_id = request.args.get('admin_id')

    if not is_admin(int(user_id) if user_id else 0):
        return jsonify({'error': 'Admin only'}), 403

    reports = load_json(REPORTS_FILE, [])

    filter_user = request.args.get('user_id')
    filter_project = request.args.get('project')
    filter_date = request.args.get('date')

    if filter_user:
        reports = [r for r in reports if str(r.get('user_id')) == str(filter_user)]
    if filter_project:
        filter_project_lower = filter_project.lower()
        reports = [r for r in reports if filter_project_lower in r.get('project', '').lower()]
    if filter_date:
        reports = [r for r in reports if r.get('date') == filter_date]

    reports = sorted(reports, key=lambda x: x.get('datetime', ''), reverse=True)

    return jsonify({'reports': reports, 'total': len(reports)})


@app.route('/api/report/<report_id>', methods=['PUT'])
def update_report(report_id):
    data = request.get_json()
    admin_id = data.get('admin_id')

    if not is_admin(int(admin_id) if admin_id else 0):
        return jsonify({'error': 'Admin only'}), 403

    reports = load_json(REPORTS_FILE, [])

    report_index = None
    for i, r in enumerate(reports):
        if r.get('id') == report_id:
            report_index = i
            break

    if report_index is None:
        return jsonify({'error': 'Report not found'}), 404

    if 'hours' in data:
        reports[report_index]['hours'] = data['hours']
    if 'project' in data:
        reports[report_index]['project'] = data['project']
    if 'comments' in data:
        reports[report_index]['comments'] = data['comments']
    if 'date' in data:
        reports[report_index]['date'] = data['date']
        old_time = reports[report_index].get('datetime', '').split(' ')[1] if ' ' in reports[report_index].get('datetime', '') else '00:00:00'
        reports[report_index]['datetime'] = f"{data['date']} {old_time}"

    save_json(REPORTS_FILE, reports)

    return jsonify({'success': True, 'report': reports[report_index]})


@app.route('/api/report/<report_id>', methods=['DELETE'])
def delete_report(report_id):
    data = request.get_json()
    admin_id = data.get('admin_id')

    if not is_admin(int(admin_id) if admin_id else 0):
        return jsonify({'error': 'Admin only'}), 403

    reports = load_json(REPORTS_FILE, [])

    original_count = len(reports)
    reports = [r for r in reports if r.get('id') != report_id]

    if len(reports) == original_count:
        return jsonify({'error': 'Report not found'}), 404

    save_json(REPORTS_FILE, reports)

    return jsonify({'success': True, 'deleted': report_id})


@app.route('/api/project', methods=['POST'])
def add_project():
    data = request.get_json()
    user_id = data.get('user_id')
    abbr = data.get('abbr', '').strip().upper()
    full = data.get('full', '').strip()

    if not is_admin(user_id):
        return jsonify({'error': 'Admin only'}), 403

    if not abbr or not full:
        return jsonify({'error': 'abbr and full required'}), 400

    projects = load_json(PROJECTS_FILE, [])

    if any(p['abbr'] == abbr for p in projects):
        return jsonify({'error': 'Project already exists'}), 400

    projects.append({'abbr': abbr, 'full': full})
    save_json(PROJECTS_FILE, projects)

    return jsonify({'success': True, 'project': {'abbr': abbr, 'full': full}})


@app.route('/api/project/<abbr>', methods=['DELETE'])
def remove_project(abbr):
    data = request.get_json()
    user_id = data.get('user_id')

    if not is_admin(user_id):
        return jsonify({'error': 'Admin only'}), 403

    projects = load_json(PROJECTS_FILE, [])
    projects = [p for p in projects if p['abbr'] != abbr]
    save_json(PROJECTS_FILE, projects)

    return jsonify({'success': True, 'deleted': abbr})


@app.route('/api/assign', methods=['POST'])
def assign_projects():
    data = request.get_json()
    admin_id = data.get('admin_id')
    target_user_id = data.get('user_id')
    abbrs = data.get('abbrs', [])

    if not is_admin(admin_id):
        return jsonify({'error': 'Admin only'}), 403

    if not target_user_id:
        return jsonify({'error': 'user_id required'}), 400

    assignments = load_json(USER_PROJECTS_FILE, {})
    assignments[str(target_user_id)] = abbrs
    save_json(USER_PROJECTS_FILE, assignments)

    return jsonify({'success': True, 'user_id': target_user_id, 'projects': abbrs})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
