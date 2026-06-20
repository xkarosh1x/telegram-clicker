import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Supabase credentials not set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/api', methods=['GET', 'POST'])
def handle_user():
    if request.method == 'GET':
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({'error': 'userId required'}), 400

        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if response.data:
                return jsonify(response.data[0])
            else:
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
                supabase.table('users').insert(new_user).execute()
                return jsonify(new_user)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif request.method == 'POST':
        data = request.json
        user_id = data.get('userId')
        if not user_id:
            return jsonify({'error': 'userId required'}), 400

        try:
            update_data = {
                'balance': data.get('balance', 0),
                'click_power': data.get('clickPower', 1),
                'total_clicks': data.get('totalClicks', 0),
                'auto_power': data.get('autoPower', 0),
                'ref_count': data.get('refCount', 0),
                'total_earned': data.get('totalEarned', 0),
                'skin': data.get('skin', 'default'),
                'daily_bonus_claimed': data.get('dailyBonusClaimed', False),
                'last_daily_bonus': data.get('lastDailyBonus', ''),
                'updated_at': datetime.utcnow().isoformat()
            }
            supabase.table('users').update(update_data).eq('user_id', user_id).execute()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

# Для локального запуска (не используется на Vercel)
if __name__ == '__main__':
    app.run(debug=True, port=5000)
