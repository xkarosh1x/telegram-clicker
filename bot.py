import os
import logging
import requests
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

WEBAPP_URL = os.environ.get('WEBAPP_URL', 'https://xkarosh1x.github.io/telegram-clicker')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Supabase credentials not set!")
    exit(1)

# --- ИМПОРТЫ TELEGRAM ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===================================================================
# 1. SUPABASE CLIENT
# ===================================================================
class SupabaseClient:
    def __init__(self, url, key):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json'
        }
    
    def table(self, table_name):
        return SupabaseTable(self.url, self.headers, table_name)

class SupabaseTable:
    def __init__(self, url, headers, table_name):
        self.url = url
        self.headers = headers
        self.table_name = table_name
    
    def select(self, columns='*'):
        self.columns = columns
        return self
    
    def eq(self, column, value):
        self.filter_column = column
        self.filter_value = value
        return self
    
    def order(self, column, desc=False):
        self.order_column = column
        self.order_desc = desc
        return self
    
    def limit(self, limit):
        self.limit_value = limit
        return self
    
    def execute(self):
        params = {'select': self.columns}
        if hasattr(self, 'filter_column'):
            params[self.filter_column] = f'eq.{self.filter_value}'
        if hasattr(self, 'order_column'):
            params['order'] = f'{self.order_column}.desc' if self.order_desc else f'{self.order_column}.asc'
        if hasattr(self, 'limit_value'):
            params['limit'] = self.limit_value
        
        url = f"{self.url}/rest/v1/{self.table_name}"
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Supabase select error: {response.status_code} - {response.text}")
            return []
    
    def insert(self, data):
        url = f"{self.url}/rest/v1/{self.table_name}"
        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code in [200, 201]:
            return response.json()
        else:
            logger.error(f"Supabase insert error: {response.status_code} - {response.text}")
            return None
    
    def update(self, data):
        self.update_data = data
        return self
    
    def eq_for_update(self, column, value):
        self.update_filter_column = column
        self.update_filter_value = value
        return self
    
    def execute_update(self):
        url = f"{self.url}/rest/v1/{self.table_name}"
        params = {self.update_filter_column: f'eq.{self.update_filter_value}'}
        response = requests.patch(url, headers=self.headers, json=self.update_data, params=params)
        if response.status_code in [200, 204]:
            return True
        else:
            logger.error(f"Supabase update error: {response.status_code} - {response.text}")
            return False

supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)

# ===================================================================
# 2. ФУНКЦИИ РАБОТЫ С БАЗОЙ
# ===================================================================
def get_or_create_user(user_id: str):
    try:
        result = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if result and len(result) > 0:
            return result[0]
        new_user = {
            'user_id': user_id,
            'balance': 0,
            'click_power': 1,
            'total_clicks': 0,
            'auto_power': 0,
            'ref_count': 0,
            'total_earned': 0,
            'skin': 'default',
            'daily_bonus_claimed': False,
            'last_daily_bonus': '',
            'created_at': datetime.utcnow().isoformat()
        }
        supabase.table('users').insert(new_user)
        return new_user
    except Exception as e:
        logger.error(f"DB error: {e}")
        return None

def update_user(user_id: str, data: dict):
    try:
        return supabase.table('users').update(data).eq_for_update('user_id', user_id).execute_update()
    except Exception as e:
        logger.error(f"Update error: {e}")
        return False

# ===================================================================
# 3. ОБРАБОТЧИКИ
# ===================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.args and context.args[0].startswith('ref_'):
        try:
            import base64
            ref_code = context.args[0][4:]
            decoded = base64.b64decode(ref_code + '==' * (4 - len(ref_code) % 4)).decode()
            referrer_id = decoded.split(':')[0]
            if referrer_id != user_id:
                referrer = get_or_create_user(referrer_id)
                if referrer:
                    update_user(referrer_id, {
                        'balance': referrer.get('balance', 0) + 50,
                        'ref_count': referrer.get('ref_count', 0) + 1
                    })
                    await update.message.reply_text("🎉 Вы пригласили друга и получили 50 🪙!")
        except Exception as e:
            logger.error(f"Referral error: {e}")
    
    user = get_or_create_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка базы данных.")
        return
    keyboard = [
        [InlineKeyboardButton("🎮 Открыть Кликер", web_app={'url': WEBAPP_URL})],
        [
            InlineKeyboardButton("📊 Статистика", callback_data='stats'),
            InlineKeyboardButton("🏆 Топ", callback_data='top')
        ],
        [
            InlineKeyboardButton("🎁 Бонус", callback_data='daily_bonus'),
            InlineKeyboardButton("👥 Рефералы", callback_data='ref_info')
        ]
    ]
    username = update.effective_user.first_name or "Игрок"
    await update.message.reply_text(
        f"🪙 *Привет, {username}!*\n\n"
        f"💰 Баланс: `{user.get('balance', 0)}`\n"
        f"💪 Сила клика: `{user.get('click_power', 1)}`\n"
        f"👥 Рефералов: `{user.get('ref_count', 0)}`\n\n"
        "👇 Нажми на кнопку, чтобы начать!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    user = get_or_create_user(user_id)
    if not user:
        await query.edit_message_text("❌ Ошибка.")
        return
    if query.data == 'stats':
        text = (
            "📊 *Твоя статистика*\n\n"
            f"💰 Баланс: `{user.get('balance', 0)}`\n"
            f"💪 Сила клика: `{user.get('click_power', 1)}`\n"
            f"🤖 Автокликер: `{user.get('auto_power', 0)}/сек`\n"
            f"👆 Всего кликов: `{user.get('total_clicks', 0)}`\n"
            f"👥 Рефералов: `{user.get('ref_count', 0)}`"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
    elif query.data == 'top':
        try:
            result = supabase.table('users').select('user_id, balance').order('balance', desc=True).limit(10).execute()
            if result:
                text = "🏆 *Топ-10 игроков*\n\n"
                for i, u in enumerate(result, 1):
                    name = f"Игрок {u['user_id'][:6]}"
                    text += f"{i}. {name} — 🪙 {u['balance']}\n"
                await query.edit_message_text(text, parse_mode='Markdown')
            else:
                await query.edit_message_text("Пока нет игроков")
        except Exception as e:
            logger.error(f"Top error: {e}")
            await query.edit_message_text("❌ Ошибка загрузки топа")
    elif query.data == 'daily_bonus':
        today = datetime.utcnow().date().isoformat()
        if user.get('last_daily_bonus') == today:
            await query.edit_message_text("❌ Ты уже получил бонус сегодня! Завтра приходи 🎁")
            return
        bonus = 100
        new_balance = user.get('balance', 0) + bonus
        new_earned = user.get('total_earned', 0) + bonus
        update_user(user_id, {
            'balance': new_balance,
            'total_earned': new_earned,
            'last_daily_bonus': today
        })
        await query.edit_message_text(
            f"🎁 *Ежедневный бонус!*\n\n"
            f"💰 +{bonus} 🪙\n"
            f"📊 Баланс: `{new_balance}`",
            parse_mode='Markdown'
        )
    elif query.data == 'ref_info':
        import base64
        code = base64.b64encode(f"{user_id}:{datetime.utcnow().timestamp()}".encode()).decode()[:16]
        ref_code = f"ref_{code}"
        link = f"https://t.me/{context.bot.username}?start={ref_code}"
        text = (
            "👥 *Реферальная система*\n\n"
            f"👤 За каждого друга: +50 🪙\n"
            f"👥 Приглашено: `{user.get('ref_count', 0)}`\n\n"
            f"📋 Твоя ссылка:\n`{link}`"
        )
        keyboard = [[InlineKeyboardButton("📋 Копировать ссылку", callback_data='copy_ref')]]
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif query.data == 'copy_ref':
        import base64
        code = base64.b64encode(f"{user_id}:{datetime.utcnow().timestamp()}".encode()).decode()[:16]
        ref_code = f"ref_{code}"
        link = f"https://t.me/{context.bot.username}?start={ref_code}"
        await query.edit_message_text(
            f"📋 *Твоя реферальная ссылка:*\n\n`{link}`\n\n👆 Скопируй и отправь друзьям!",
            parse_mode='Markdown'
        )

# ===================================================================
# 4. HEALTH-СЕРВЕР
# ===================================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"Health server running on port {port}")
    server.serve_forever()

# ===================================================================
# 5. ОЧИСТКА ВЕБХУКА И СБРОС ОБНОВЛЕНИЙ (без logout)
# ===================================================================
def clear_webhook_and_updates():
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        resp = requests.get(url)
        logger.info(f"deleteWebhook: {resp.json()}")
    except Exception as e:
        logger.error(f"deleteWebhook error: {e}")
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
        resp = requests.get(url, params={'offset': -1, 'timeout': 1})
        logger.info(f"getUpdates clear: {resp.json()}")
    except Exception as e:
        logger.error(f"getUpdates error: {e}")
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        resp = requests.get(url, params={'url': ''})
        logger.info(f"setWebhook empty: {resp.json()}")
    except Exception as e:
        logger.error(f"setWebhook error: {e}")

# ===================================================================
# 6. MAIN
# ===================================================================
def main():
    # Очистка перед запуском (без logout)
    clear_webhook_and_updates()
    
    # Запускаем health-сервер
    thread = threading.Thread(target=run_health_server, daemon=True)
    thread.start()
    
    # Создаём приложение
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("Бот запущен, начинаем polling...")
    
    # Запускаем polling с защитой от конфликтов
    while True:
        try:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                timeout=30,
                poll_interval=1.0
            )
        except Exception as e:
            logger.error(f"Polling error: {e}")
            if "Conflict" in str(e):
                logger.info("Обнаружен конфликт, перезапуск через 10 секунд...")
                time.sleep(10)
                clear_webhook_and_updates()
                continue  # перезапускаем цикл
            else:
                raise

if __name__ == '__main__':
    main()
