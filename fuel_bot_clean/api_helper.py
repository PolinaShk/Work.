import http.client
import json
import codecs
from datetime import datetime, timedelta

url = 'api.opti-24.ru'
post_endpoint = '/vip/v1/authUser'
api_key = 'GPN.02231083b9400e0078b24d65677fe0b8fcb85193.08902e4def7b9a012f47ce1cd6a51a088564945c'

AUTH_DATA = {
    'login': 'ideast',
    'password': '8d9ce1e59bd5e3c4a4532200dcb41027c8718aa35e0ef0bbc180d3cb60a259f36da7a8856a366fbfb5f0ef6ea9e67c07adb1a7778db9682c7e768e9b813fb310'
}

def authenticate():
    headers = {'Content-Type': 'application/json', 'api_key': api_key}
    conn = http.client.HTTPSConnection(url)
    try:
        conn.request("POST", post_endpoint, json.dumps(AUTH_DATA), headers)
        response = conn.getresponse()
        data = json.loads(codecs.decode(response.read().decode(), 'unicode_escape'))
        
        session_id = data.get('data', {}).get('session_id')
        contracts = data.get('data', {}).get('contracts', [])
        
        contract_id = None
        for contract in contracts:
            if contract.get('cards_count', 0) > 0:
                contract_id = contract.get('id')
                print(f"✅ Контракт с картами: {contract.get('number')}")
                break
        
        if not contract_id and contracts:
            contract_id = contracts[0].get('id')
            
        return session_id, contract_id
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return None, None
    finally:
        conn.close()

def fetch_transaction_data():
    session_id, contract_id = authenticate()
    if not session_id or not contract_id:
        print("⚠️ Не удалось получить session_id или contract_id")
        return None
        
    current_date = datetime.now()
    date_to = current_date.strftime("%Y-%m-%d")
    date_from = (current_date - timedelta(days=27)).strftime("%Y-%m-%d")

    headers = {
        'Content-Type': 'application/json',
        'api_key': api_key,
        'session_id': session_id,
        'contract_id': str(contract_id),
    }

    conn = http.client.HTTPSConnection(url)
    try:
        conn.request("GET", f'/vip/v2/transactions?date_from={date_from}&date_to={date_to}&page_limit=25', headers=headers)
        transactions = json.loads(conn.getresponse().read().decode('unicode_escape'))
        
        conn.request("GET", f'/vip/v1/getPartContractData?contract_id={contract_id}', headers=headers)
        contract_data = json.loads(conn.getresponse().read().decode('unicode_escape'))
        
        conn.request("GET", f'/vip/v2/cards?status=Active&page=1&on_page=18', headers=headers)
        cards_data = json.loads(conn.getresponse().read().decode('unicode_escape'))
    except Exception as e:
        print(f"❌ Ошибка получения данных от API: {e}")
        return None
    finally:
        conn.close()

    time_stack, card_stack, cost_stack, comment_stack, number_stack = [], [], [], [], []
    balance = 0

    for item in sorted(transactions.get('data', {}).get('result', []), key=lambda x: x.get('timestamp', ''), reverse=True)[:5]:
        if item.get('timestamp'): time_stack.append(item['timestamp'])
        if item.get('card_number'): card_stack.append(item['card_number'])
        if item.get('sum_no_discount'): cost_stack.append(float(item['sum_no_discount']))

    balance = float(contract_data.get('data', {}).get('balanceData', {}).get('balance', 0))

    for item in cards_data.get('data', {}).get('result', []):
        if item.get('number'): number_stack.append(item['number'])
        if item.get('comment'): comment_stack.append(item.get('comment', 'нет комментария'))

    return {
        'time_stack': time_stack,
        'card_number_stack': card_stack,
        'base_cost_5_stack': cost_stack,
        'balance': balance,
        'comment_stack': comment_stack,
        'number_stack': number_stack
    }