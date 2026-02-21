# ⚡ Quick Start — 3 минуты до релиза

## 1️⃣ Настройка (1 мин)

### Открой `telegram_bot.py`:
```python
# Строка ~30 — замени на свой GitHub Pages URL:
WEBAPP_URL = 'https://твой-username.github.io/telegram-bot-webapp/'
```

### Открой `telegram-bot.service`:
```
# Строка 7 — вставь токен РАБОЧЕГО бота:
Environment="TELEGRAM_BOT_TOKEN=123456:ABC-DEF..."
```

---

## 2️⃣ Загрузи Web App на GitHub (1 мин)

```
1. github.com → telegram-bot-webapp
2. Замени index.html новым файлом
3. Commit changes
4. Подожди 2 минуты
```

---

## 3️⃣ Деплой на сервер (1 мин)

### Автоматически:
```bash
./deploy.sh
```

### Вручную:
```bash
scp telegram_bot.py vpsbg:~/telegram_bot.py
scp telegram-bot.service vpsbg:~/telegram-bot.service
ssh vpsbg "sudo mv ~/telegram-bot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart telegram-bot"
```

---

## ✅ Готово!

Открой Telegram → Рабочий бот → `/start` → **📱 Открыть приложение**

---

**Проблемы?** Читай `RELEASE_GUIDE.md` для детальной инструкции.
