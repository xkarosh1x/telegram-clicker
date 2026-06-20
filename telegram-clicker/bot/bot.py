import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client, Client

# --- Config ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEBAPP_URL = 'https://github.com/xkarosh1x/telegram-clicker'  # GitHub Pages URL

# Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Проверяем/создаем пользователя в БД
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if not response.data:
            supabase.table('users').insert({
                'user_id': user_id,
                'balance': 0,
                'click_power': 1,
                'total_clicks': 0
            }).execute()
    except Exception as e:
        print(f"DB Error: {e}")
    
    # Создаем кнопку для открытия Mini App
    keyboard = [
        [InlineKeyboardButton("🎮 Открыть Кликер", web_app={'url': WEBAPP_URL})],
        [InlineKeyboardButton("📊 Моя статистика", callback_data='stats')],
        [InlineKeyboardButton("🏆 Топ игроков", callback_data='top')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🪙 *Добро пожаловать в Кликер!*\n\n"
        "Нажимай на монетку, зарабатывай очки и покупай улучшения!\n"
        "👇 Нажми на кнопку ниже, чтобы начать играть.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    
    if query.data == 'stats':
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if response.data:
                data = response.data[0]
                text = (
                    f"📊 *Твоя статистика*\n\n"
                    f"🪙 Баланс: `{data['balance']}`\n"
                    f"💪 Сила клика: `{data['click_power']}`\n"
                    f"👆 Всего кликов: `{data['total_clicks']}`"
                )
                await query.edit_message_text(text, parse_mode='Markdown')
            else:
                await query.edit_message_text("❌ Данные не найдены")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")
    
    elif query.data == 'top':
        try:
            response = supabase.table('users')\
                .select('user_id, balance')\
                .order('balance', desc=True)\
                .limit(10)\
                .execute()
            
            if response.data:
                text = "🏆 *Топ-10 игроков*\n\n"
                for i, user in enumerate(response.data, 1):
                    # Получаем username из Telegram (если есть)
                    name = f"Игрок {user['user_id'][:6]}"
                    text += f"{i}. {name} — 🪙 {user['balance']}\n"
                await query.edit_message_text(text, parse_mode='Markdown')
            else:
                await query.edit_message_text("Пока нет игроков")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
