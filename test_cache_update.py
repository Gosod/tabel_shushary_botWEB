#!/usr/bin/env python3
"""
Тестовый скрипт для проверки логики очистки кеша при обновлении версии бота.
Проверяет, что:
1. При смене версии сбрасывается состояние (user_data).
2. Данные отчетов (reports.json) и пользователей (users.json) НЕ удаляются.
"""

import os
import json
import sys
from datetime import datetime

# Импортируем функции из основного бота
# Убедитесь, что telegram_bot.py находится в той же папке или в PYTHONPATH
from telegram_bot import (
    BOT_VERSION, 
    CACHE_FILE, 
    REPORTS_FILE, 
    USERS_FILE, 
    DataManager, 
    clear_user_cache
)
from telegram import Update, User
from telegram.ext import ContextTypes

class MockContext:
    """Заглушка для контекста Telegram бота"""
    def __init__(self):
        self.user_data = {
            "some_old_state": "data_to_clear",
            "project_selection": "old_project",
            "step": "waiting_for_input"
        }

def setup_test_data(user_id: int):
    """Создает тестовые данные: старую версию в кеше и важные данные в файлах"""
    print(f"--- Подготовка тестовых данных для пользователя {user_id} ---")
    
    # 1. Эмулируем СТАРУЮ версию в кеше
    cache = DataManager.load_json(CACHE_FILE, {})
    cache[str(user_id)] = {"version": "1.0.0", "cleared_at": "2023-01-01T00:00:00"}
    DataManager.save_json(CACHE_FILE, cache)
    print(f"✅ Записана старая версия (1.0.0) в {CACHE_FILE}")
    
    # 2. Создаем фейковые ОТЧЕТЫ (они должны сохраниться!)
    # Структура reports.json - это СПИСОК объектов, а не словарь
    reports = DataManager.load_json(REPORTS_FILE, [])
    if not isinstance(reports, list):
        reports = []
    # Добавляем тестовый отчет
    test_report = {
        "id": f"test_{user_id}",
        "user_id": user_id,
        "username": "test_user",
        "project": "Test Project",
        "hours": 8, 
        "comments": "Important report",
        "date": "2024-05-20",
        "datetime": "2024-05-20 10:00:00"
    }
    reports.append(test_report)
    DataManager.save_json(REPORTS_FILE, reports)
    print(f"✅ Создан тестовый отчет в {REPORTS_FILE}")
    
    # 3. Создаем фейкового ПОЛЬЗОВАТЕЛЯ (он должен сохраниться!)
    # Структура users.json может быть списком или словарем - проверяем
    users_data = DataManager.load_json(USERS_FILE, [])
    if isinstance(users_data, list):
        # Если список - ищем пользователя или добавляем нового
        found = False
        for user in users_data:
            if user.get("user_id") == user_id or user.get("id") == str(user_id):
                user["name"] = "Test User"
                user["role"] = "employee"
                found = True
                break
        if not found:
            users_data.append({"user_id": user_id, "id": str(user_id), "name": "Test User", "role": "employee"})
        users = {str(user_id): u for u in users_data} # Для проверки ниже создаем мапу
        DataManager.save_json(USERS_FILE, users_data)
    else:
        # Если словарь
        users_data[str(user_id)] = {"name": "Test User", "role": "employee"}
        users = users_data
        DataManager.save_json(USERS_FILE, users_data)
        
    print(f"✅ Создан тестовый пользователь в {USERS_FILE}")
    
    return MockContext()

def run_test(user_id: int):
    """Запускает проверку"""
    print(f"\n--- ЗАПУСК ТЕСТА (Текущая версия бота: {BOT_VERSION}) ---\n")
    
    context = setup_test_data(user_id)
    
    # Проверяем состояние ДО очистки
    print(f"Состояние user_data ДО очистки: {context.user_data}")
    
    # Вызываем функцию очистки (как это делается в /start)
    is_cleared = clear_user_cache(user_id, context)
    
    # Проверяем состояние ПОСЛЕ
    print(f"Состояние user_data ПОСЛЕ очистки: {context.user_data}")
    
    # Проверяем файлы данных
    reports = DataManager.load_json(REPORTS_FILE, [])
    users_data = DataManager.load_json(USERS_FILE, [])
    cache = DataManager.load_json(CACHE_FILE, {})
    
    print("\n--- РЕЗУЛЬТАТЫ ПРОВЕРКИ ---")
    
    success = True
    
    # 1. Проверка сброса состояния
    if not context.user_data:
        print("✅ PASS: Состояние диалога (user_data) успешно сброшено.")
    else:
        print("❌ FAIL: Состояние диалога НЕ сброшено!")
        success = False
        
    # 2. Проверка сохранения отчетов (ищем по user_id в списке)
    reports_found = False
    if isinstance(reports, list):
        for report in reports:
            if report.get("user_id") == user_id or report.get("id", "").startswith(str(user_id)):
                reports_found = True
                break
    elif isinstance(reports, dict) and str(user_id) in reports and len(reports[str(user_id)]) > 0:
        reports_found = True
        
    if reports_found:
        print(f"✅ PASS: Отчеты сохранены.")
    else:
        print("❌ FAIL: Отчеты были удалены! Это критическая ошибка.")
        success = False
        
    # 3. Проверка сохранения пользователей (ищем по user_id в списке или словаре)
    users_found = False
    if isinstance(users_data, list):
        for user in users_data:
            if user.get("user_id") == user_id or user.get("id") == str(user_id):
                users_found = True
                break
    elif isinstance(users_data, dict) and str(user_id) in users_data:
        users_found = True
        
    if users_found:
        print(f"✅ PASS: Данные пользователя сохранены.")
    else:
        print("❌ FAIL: Данные пользователя удалены!")
        success = False
        
    # 4. Проверка обновления версии в кеше
    current_version = cache.get(str(user_id), {}).get("version")
    if current_version == BOT_VERSION:
        print(f"✅ PASS: Версия в кеше обновлена до {BOT_VERSION}.")
    else:
        print(f"❌ FAIL: Версия в кеше не обновлена (текущая: {current_version}).")
        success = False
        
    # 5. Проверка флага возврата
    if is_cleared:
        print("✅ PASS: Функция вернула True (очистка произведена).")
    else:
        print("❌ FAIL: Функция вернула False (ошибка логики).")
        success = False

    print("\n" + "="*40)
    if success:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("Можно смело деплоить на сервер.")
    else:
        print("⚠️ ОБНАРУЖЕНЫ ОШИБКИ! Требуется вмешательство.")
    print("="*40)
    
    return success

if __name__ == "__main__":
    # Используем фиктивный ID для теста
    TEST_USER_ID = 123456789
    try:
        run_test(TEST_USER_ID)
    except Exception as e:
        print(f"❌ Критическая ошибка при выполнении теста: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
