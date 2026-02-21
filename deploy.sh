#!/bin/bash
set -e

echo "🚀 Deploying Telegram Bot to Server..."

# 1. Копируем файлы на сервер
echo "📦 Copying files..."
scp telegram_bot.py vpsbg:~/telegram_bot.py
scp telegram-bot.service vpsbg:~/telegram-bot.service

# 2. Обновляем systemd service
echo "⚙️  Updating systemd service..."
ssh vpsbg << 'EOF'
sudo mv ~/telegram-bot.service /etc/systemd/system/telegram-bot.service
sudo systemctl daemon-reload
EOF

# 3. Перезапускаем бота
echo "🔄 Restarting bot..."
ssh vpsbg "sudo systemctl restart telegram-bot"

# 4. Проверяем статус
echo "✅ Checking status..."
ssh vpsbg "sudo systemctl status telegram-bot --no-pager -l"

echo ""
echo "🎉 Deployment complete!"
echo "📊 Check logs: ssh vpsbg 'sudo journalctl -u telegram-bot -f'"
