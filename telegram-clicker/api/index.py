import json
import os
from datetime import datetime
from supabase import create_client, Client
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Supabase ---
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/api', methods=['GET', 'POST'])
def handle_user():
    if request.method == 'GET':
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({'error': 'userId required'}), 400
        
        # Получаем данные пользователя
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if response.data:
                return jsonify(response.data[0])
            else:
                # Создаем нового пользователя
                new_user = {
                    'user_id': user_id,
                    'balance': 0,
                    'click_power': 1,
                    'total_clicks': 0,
                    'created_at': datetime.utcnow().isoformat()
                }
                supabase.table('users').insert(new_user).execute()
                return jsonify(new_user)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        data = request.json
        user_id = data.get('userId')
        balance = data.get('balance', 0)
        click_power = data.get('clickPower', 1)
        total_clicks = data.get('totalClicks', 0)
        
        if not user_id:
            return jsonify({'error': 'userId required'}), 400
        
        try:
            # Обновляем данные
            supabase.table('users').update({
                'balance': balance,
                'click_power': click_power,
                'total_clicks': total_clicks,
                'updated_at': datetime.utcnow().isoformat()
            }).eq('user_id', user_id).execute()
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run()
