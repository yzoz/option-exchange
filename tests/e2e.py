#!/usr/bin/env python3
"""E2E-дым-тест YZoZ Option Exchange.

Проверяет сквозной сценарий целиком против ЖИВОГО стека
(API + Mongo + Memcached + InfluxDB). Юнит-тестов в проекте нет —
единственный вид тестов здесь e2e (см. docs/DEVELOPER_GUIDE.md §0.2).

Запуск (из корня репозитория, при поднятом API):

    # 1) поднять хранилища и API
    docker compose up -d
    PY_MODE=dev python api/app.py &          # API на :6969

    # 2) прогнать сценарий
    .venv/bin/python tests/e2e.py

Адрес API берётся из переменной окружения API_URL (по умолчанию
http://localhost:6969). Скрипт завершается кодом 1 при первой неудаче.

!! ВАЖНО ДЛЯ БУДУЩИХ АГЕНТОВ !!
После каждого крупного тематического блока правок ДОПОЛНЯЙТЕ этот скрипт
проверками, покрывающими именно ваши изменения (новый роут, новая логика
матчинга, новые поля и т.п.), и держите его зелёным. См.
docs/DEVELOPER_GUIDE.md §0.3.
"""

import hashlib
import hmac
import json
import os
import random
import string
import sys
import threading
import time
import urllib.error
import urllib.request

# Читаем .env (как API), чтобы взять RATE_WINDOW/RATE_MAX из того же конфига.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))
except ImportError:
    pass

API = os.getenv('API_URL', 'http://localhost:6969')
TICKER = 'ETH_BTC'
# Серия/страйк из exchange/instruments.json. После задачи ТЗ #17 (регенерация
# серий) обновите ASSET на актуальную серию, иначе часть доступа отвалится.
ASSET = 'ETH_BTC_1519862400_100000_C'
PRICE = 30000


def reset_exchange_state():
    """Очистить заявки и контракты, чтобы сценарий был детерминирован.

    Без этого оставшиеся от прошлых прогонов встречные заявки ломают
    ожидания (sell сразу матчится вместо постановки лимита). Пользователей
    не трогаем — тест создаёт собственных. Отключается E2E_RESET=0.
    """
    if os.getenv('E2E_RESET', '1') == '0':
        return False
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'api'))
    try:
        from inc.settings import modb
    except ImportError as e:
        print('reset пропущен (нет inc.settings: %s)' % e)
        return False
    db = modb()
    db.orders.delete_many({})
    db.contracts.delete_many({})
    return True


def _post(path, payload):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        return urllib.request.urlopen(req, timeout=15).read().decode()
    except urllib.error.HTTPError as e:
        return 'HTTP %s: %s' % (e.code, e.read().decode())


def _mac(password, message):
    return hmac.new(password.encode(), message.encode(), hashlib.sha3_512).hexdigest()


class Client:
    def __init__(self, key, password, seed):
        self.key = key
        self.password = password
        self.seed = seed

    def signup(self):
        return _post('/signup', {'key': self.key, 'seed': self.seed,
                                 'password': self.password, 'email': self.key + '@e2e.local'})

    def ask(self, question):
        return _post('/user', {'user': self.key, 'password': self.password,
                               'hmac': _mac(self.password, question), 'question': question})

    def order(self, type, quant, price, asset=ASSET, action='send'):
        msg = action + type + str(quant) + asset + str(price)
        return _post('/order', {'user': self.key, 'password': self.password,
                                'hmac': _mac(self.password, msg),
                                'question': {'action': action, 'type': type,
                                             'quant': quant, 'asset': asset, 'price': price}})


def newClient(tag):
    suffix = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    key = 'E2E-%s-%s' % (tag, suffix)
    return Client(key, 'pw-' + suffix, 'seed ' + suffix)


# --- инфраструктура проверок -------------------------------------------------

_checks = 0
_failures = []


def check(label, condition, detail=''):
    global _checks
    _checks += 1
    if condition:
        print('  ok  %s' % label)
    else:
        print('  FAIL %s %s' % (label, detail))
        _failures.append(label)


def has_quant(contracts_json, expected):
    """Проверяет суммарный quant по ASSET в ответе /user?contracts."""
    docs = json.loads(contracts_json)
    for doc in docs:
        if doc['asset'] == ASSET:
            return doc['quant'] == expected
    return False


def open_order_quant(orders_json):
    docs = json.loads(orders_json)
    if not docs:
        return 0
    return docs[0]['quant']


# --- сценарий ----------------------------------------------------------------

def scenario_matching():
    print('[1] Регистрация и начальный баланс')
    a, b, c = newClient('A'), newClient('B'), newClient('C')
    for u in (a, b, c):
        check('signup %s' % u.key, 'created!' in u.signup())

    check('повторный signup -> 409', '409' in _post(
        '/signup', {'key': a.key, 'seed': a.seed, 'password': a.password}))

    bal = json.loads(b.ask('balances'))
    check('начальный баланс ETH=1000', bal['own']['ETH'] == 1000, str(bal['own']))
    check('начальный баланс BTC=100000000', bal['own']['BTC'] == 100000000, str(bal['own']))

    print('[2] Частичное исполнение')
    check('A sell 10 -> лимит', 'SendLimit' in a.order('sell', 10, PRICE))
    check('B buy 4 -> сделка', 'Deal' in b.order('buy', 4, PRICE))
    check('A позиция -4', has_quant(a.ask('contracts'), -4), a.ask('contracts'))
    check('A остаток заявки 6', open_order_quant(a.ask('orders')) == 6, a.ask('orders'))

    print('[3] Полное закрытие остатка')
    check('C buy 6 -> сделка', 'Deal' in c.order('buy', 6, PRICE))
    check('A позиция -10', has_quant(a.ask('contracts'), -10), a.ask('contracts'))
    check('A заявок не осталось', open_order_quant(a.ask('orders')) == 0, a.ask('orders'))

    print('[4] Атомарность: параллельные встречные ордера')
    a2, b2, c2 = newClient('A2'), newClient('B2'), newClient('C2')
    for u in (a2, b2, c2):
        u.signup()
    check('A2 sell 10 -> лимит', 'SendLimit' in a2.order('sell', 10, PRICE))

    results = {}

    def buy(name, u):
        results[name] = u.order('buy', 10, PRICE)

    t1 = threading.Thread(target=buy, args=('b2', b2))
    t2 = threading.Thread(target=buy, args=('c2', c2))
    t1.start(); t2.start(); t1.join(); t2.join()
    deals = sum(1 for r in results.values() if 'Deal' in r)
    check('ровно один матч на 10', deals == 1, str(results))
    check('A2 позиция -10 (не -20)', has_quant(a2.ask('contracts'), -10), a2.ask('contracts'))

    print('[5] Негативные проверки')
    bad = Client(a.key, 'wrong-password', a.seed)
    check('неверный пароль -> 401', '401' in bad.ask('balances'))
    check('неверный HMAC -> 401',
          '401' in _post('/user', {'user': b.key, 'password': b.password,
                                   'hmac': 'deadbeef', 'question': 'balances'}))
    check('плохой asset -> 400', '400' in b.order('buy', 1, PRICE, asset='ETH_BTC_0_0_C'))
    check('quant<=0 -> 400', '400' in b.order('buy', 0, PRICE))


def scenario_rate_limit():
    """Rate-limit публичных входов: серия запросов с одного IP -> HTTP 429.

    Запускается последней, т.к. расходует бюджет лимитера для этого IP.
    Отключается E2E_RATE=0 (например, если лимитер выключен через RATE_LIMIT=0).
    """
    if os.getenv('E2E_RATE', '1') == '0':
        print('[6] Rate-limit — пропущен (E2E_RATE=0)')
        return
    rate_max = int(os.getenv('RATE_MAX', '120'))
    print('[6] Rate-limit: до %d запросов с одного IP -> 429' % rate_max)
    got_429 = False
    for _ in range(rate_max * 2 + 20):
        if '429' in _post('/user', {}):
            got_429 = True
            break
    check('серия запросов -> 429', got_429)


def main():
    print('E2E против %s' % API)
    # Дождаться чистой квоты rate-лимитера: сценарий rate-limit в конце
    # насыщает окно, поэтому повторный запуск сразу после него получил бы 429.
    if os.getenv('E2E_RATE', '1') != '0':
        time.sleep(float(os.getenv('RATE_WINDOW', '60')) + 2)
    ping = _post('/user', {})  # ожидаем 400, но главное — API отвечает
    if 'HTTP' not in ping:
        print('API не отвечает по %s' % API)
        return 1
    if reset_exchange_state():
        print('(состояние ордеров/контрактов сброшено)')
    scenario_matching()
    scenario_rate_limit()

    print('\nИтог: %d проверок, %d провалов' % (_checks, len(_failures)))
    if _failures:
        print('Провалено: %s' % ', '.join(_failures))
        return 1
    print('Все e2e-проверки пройдены.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
