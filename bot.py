import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set!")
    exit(1)

WEBAPP_URL = os.environ.get('WEBAPP_URL', 'https://твой-username.github.io/telegram-clicker')

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Supabase credentials not set!")
    exit(1)

# --- Supabase REST Client ---
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

# --- Database helpers ---
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

def get_top_users(limit=10):
    try:
        result = supabase.table('users').select('user_id, balance, total_clicks').order('balance', desc=True).limit(limit).execute()
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.error(f"Top error: {e}")
        return []

# --- Bot handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Проверяем реферальный код
    if context.args and context.args[0].startswith('ref_'):
        ref_code = context.args[0][4:]
        try:
            import base64
            decoded = base64.b64decode(ref_code + '==' * (4 - len(ref_code) % 4)).decode()
            referrer_id = decoded.split(':')[0]
            
            if referrer_id != user_id:
                referrer = get_or_create_user(referrer_id)
                if referrer:
                    new_balance = referrer.get('balance', 0) + 50
                    new_ref_count = referrer.get('ref_count', 0) + 1
                    update_user(referrer_id, {
                        'balance': new_balance,
                        'ref_count': new_ref_count
                    })
                    await update.message.reply_text(
                        "🎉 Вы пригласили нового друга и получили 50 🪙!"
                    )
                
                user = get_or_create_user(user_id)
                if user:
                    new_balance = user.get('balance', 0) + 25
                    update_user(user_id, {
                        'balance': new_balance,
                        'referred_by': referrer_id
                    })
        except Exception as e:
            logger.error(f"Referral error: {e}")
    
    user = get_or_create_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка базы данных. Попробуйте позже.")
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем username для приветствия
    username = update.effective_user.first_name or "Игрок"
    
    await update.message.reply_text(
        f"🪙 *Привет, {username}!*\n\n"
        f"💰 Баланс: `{user.get('balance', 0)}`\n"
        f"💪 Сила клика: `{user.get('click_power', 1)}`\n"
        f"👥 Приглашено друзей: `{user.get('ref_count', 0)}`\n\n"
        "👇 Нажми на кнопку, чтобы начать играть!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    user = get_or_create_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ Ошибка. Попробуйте позже.")
        return
    
    if query.data == 'stats':
        text = (
            "📊 *Твоя статистика*\n\n"
            f"💰 Баланс: `{user.get('balance', 0)}`\n"
            f"💪 Сила клика: `{user.get('click_power', 1)}`\n"
            f"🤖 Автокликер: `{user.get('auto_power', 0)}/сек`\n"
            f"👆 Всего кликов: `{user.get('total_clicks', 0)}`\n"
            f"👥 Рефералов: `{user.get('ref_count', 0)}`\n"
            f"🏅 Уровень: `{calculate_level(user.get('total_earned', 0))}`"
        )
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == 'top':
        top_users = get_top_users(10)
        if top_users:
            text = "🏆 *Топ-10 игроков*\n\n"
            for i, u in enumerate(top_users, 1):
                name = f"Игрок {u['user_id'][:6]}"
                text += f"{i}. {name} — 🪙 {u['balance']} (👆{u['total_clicks']})\n"
            await query.edit_message_text(text, parse_mode='Markdown')
        else:
            await query.edit_message_text("Пока нет игроков")
    
    elif query.data == 'daily_bonus':
        today = datetime.utcnow().date().isoformat()
        if user.get('last_daily_bonus') == today:
            await query.edit_message_text("❌ Ты уже получил бонус сегодня!\nПриходи завтра 🎁")
            return
        
        bonus = 100 + calculate_level(user.get('total_earned', 0)) * 10
        new_balance = user.get('balance', 0) + bonus
        new_earned = user.get('total_earned', 0) + bonus
        
        update_user(user_id, {
            'balance': new_balance,
            'total_earned': new_earned,
            'last_daily_bonus': today
        })
        
        await query.edit_message_text(
            f"🎁 *Ежедневный бонус получен!*\n\n"
            f"💰 +{bonus} 🪙\n"
            f"📊 Новый баланс: `{new_balance}`\n\n"
            "🔄 Возвращайся завтра за новым бонусом!",
            parse_mode='Markdown'
        )
    
    elif query.data == 'ref_info':
        ref_code = generate_ref_code(user_id)
        text = (
            "👥 *Реферальная система*\n\n"
            "Приглашай друзей и получай бонусы!\n"
            f"👤 За каждого друга: +50 🪙 тебе и +25 🪙 другу\n\n"
            f"📋 Твоя ссылка:\n"
            f"`https://t.me/{context.bot.username}?start={ref_code}`\n\n"
            f"👥 Приглашено: `{user.get('ref_count', 0)}`"
        )
        keyboard = [[InlineKeyboardButton("📋 Копировать ссылку", callback_data='copy_ref')]]
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'copy_ref':
        ref_code = generate_ref_code(user_id)
        link = f"https://t.me/{context.bot.username}?start={ref_code}"
        await query.edit_message_text(
            f"📋 *Твоя реферальная ссылка:*\n\n"
            f"`{link}`\n\n"
            "👆 Скопируй и отправь друзьям!",
            parse_mode='Markdown'
        )

def calculate_level(total_earned):
    level = 1
    while total_earned >= get_level_exp(level):
        level += 1
    return level

def get_level_exp(level):
    return int(100 * (1.5 ** (level - 1)))

def generate_ref_code(user_id):
    import base64
    code = base64.b64encode(f"{user_id}:{datetime.utcnow().timestamp()}".encode()).decode()[:16]
    return f"ref_{code}"

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🤖 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
