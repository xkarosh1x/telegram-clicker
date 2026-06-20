import os
import json
from datetime import datetime
from supabase import create_client, Client

# --- Supabase ---
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Supabase credentials not set")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def handler(request):
    """Vercel Serverless Function handler"""
    method = request.method

    if method == 'GET':
        user_id = request.args.get('userId')
        if not user_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'userId required'})
            }
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if response.data:
                return {
                    'statusCode': 200,
                    'body': json.dumps(response.data[0]),
                    'headers': {'Content-Type': 'application/json'}
                }
            else:
                # Создаём нового пользователя
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
                return {
                    'statusCode': 200,
                    'body': json.dumps(new_user),
                    'headers': {'Content-Type': 'application/json'}
                }
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }

    elif method == 'POST':
        body = request.get_json()
        if not body:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid JSON'})
            }
        user_id = body.get('userId')
        if not user_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'userId required'})
            }
        try:
            update_data = {
                'balance': body.get('balance', 0),
                'click_power': body.get('clickPower', 1),
                'total_clicks': body.get('totalClicks', 0),
                'auto_power': body.get('autoPower', 0),
                'ref_count': body.get('refCount', 0),
                'total_earned': body.get('totalEarned', 0),
                'skin': body.get('skin', 'default'),
                'daily_bonus_claimed': body.get('dailyBonusClaimed', False),
                'last_daily_bonus': body.get('lastDailyBonus', ''),
                'updated_at': datetime.utcnow().isoformat()
            }
            supabase.table('users').update(update_data).eq('user_id', user_id).execute()
            return {
                'statusCode': 200,
                'body': json.dumps({'success': True}),
                'headers': {'Content-Type': 'application/json'}
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }

    else:
        return {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method not allowed'})
        }
