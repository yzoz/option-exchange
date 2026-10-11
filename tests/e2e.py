#!/usr/bin/env python3
"""E2E-дым-тест YZoZ Option Exchange.

Проверяет сквозной сценарий целиком против ЖИВОГО стека
(API + Mongo + Memcached + InfluxDB). Юнит-тестов в проекте нет —
единственный вид тестов здесь e2e (см. docs/DEVELOPER_GUIDE.md §0.2).

Запуск (из корня репозитория, при поднятом API):

    # 1) поднять хранилища и API
    docker compose up -d
    #    (setsid/nohup — чтобы сервер пережил завершение оболочки; голый '&'
    #     в агентской среде убивается вместе с командой, см. GUIDE §7.1)
    setsid nohup env PY_MODE=dev python api/app.py >/tmp/opencode/oe-api.log 2>&1 </dev/null &

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
# Веб-слой (задача #24 — его /health). E2E_WEB=0 отключает проверку, если
# тест гоняется против одного API без Node-сервера.
WEB = os.getenv('WEB_URL', 'http://localhost:3000')
TICKER = 'ETH_BTC'
# Серия/страйк из exchange/instruments.json. Задача ТЗ #17 регенерировала серии
# (актуальные, в будущем) — при следующем обновлении серий синхронизируйте эти
# константы, иначе сценарий отвалится на несуществующем активе.
EXP = '1793491200'
ASSET = 'ETH_BTC_%s_50000_C' % EXP
# Отдельный страйк для сценария правки заявки, чтобы не пересекаться с матчингом.
EDIT_ASSET = 'ETH_BTC_%s_45000_C' % EXP
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


def _get(path):
    try:
        return urllib.request.urlopen(API + path, timeout=15).read().decode()
    except urllib.error.HTTPError as e:
        return 'HTTP %s: %s' % (e.code, e.read().decode())


def _get_url(url):
    """GET по абсолютному URL (для проверок веб-слоя, задача #24)."""
    try:
        return urllib.request.urlopen(url, timeout=15).read().decode()
    except urllib.error.HTTPError as e:
        return 'HTTP %s: %s' % (e.code, e.read().decode())
    except urllib.error.URLError as e:
        return 'URL ERROR: %s' % e


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

    def _order_raw(self, payload, msg):
        return _post('/order', {'user': self.key, 'password': self.password,
                                'hmac': _mac(self.password, msg),
                                'question': payload})

    def remove(self, id):
        return self._order_raw({'action': 'remove', 'id': id}, 'remove' + str(id))

    def edit(self, id, quant, price):
        return self._order_raw({'action': 'edit', 'id': id, 'quant': quant, 'price': price},
                               'edit' + str(id) + str(quant) + str(price))

    def open_order(self):
        docs = json.loads(self.ask('orders'))
        return docs[0] if docs else None


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
    t1.start()
    t2.start()
    t1.join()
    t2.join()
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
    check('недостаточно средств -> 400', '400' in a.order('sell', 999999999, PRICE))

    # Задача #16: ошибки отдаются реальным HTTP-кодом и единым JSON-телом
    # {"error": {"code", "message"}} — а не «200 + текст».
    err = _post('/user', {})
    check('ошибка в едином формате', '"error"' in err and '"code": 400' in err, err)
    try:
        req = urllib.request.Request(API + '/user', data=b'{}',
                                     headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=15)
        code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    check('ошибка с настоящим HTTP-кодом (не 200)', code == 400, str(code))


def scenario_edit():
    """Задача #14: правка лимитной заявки (edit) и её частные случаи."""
    print('[7] Правка заявки (edit)')
    e = newClient('E')
    check('signup E', 'created!' in e.signup())
    check('E sell -> лимит', 'SendLimit' in e.order('sell', 5, PRICE, asset=EDIT_ASSET))
    order = e.open_order()
    check('у E есть заявка 5', order is not None and order['quant'] == 5, str(order))

    check('edit -> Edit', 'Edit' in e.edit(order['id'], 8, PRICE + 1000), e.edit(order['id'], 8, PRICE + 1000))
    order = e.open_order()
    check('quant изменён на 8', order['quant'] == 8, str(order))
    check('price изменён', order['price'] == PRICE + 1000, str(order))

    check('edit quant<=0 -> 400', '400' in e.edit(order['id'], 0, PRICE))
    check('edit несуществующей -> 404',
          '404' in e.edit('000000000000000000000000', 1, PRICE))
    check('remove своей заявки', 'Remove' in e.remove(order['id']))
    check('после remove заявок нет', e.open_order() is None)

    # Чужой не может править/снимать заявку (задача #15/#16 — 404, не 500).
    f = newClient('F')
    f.signup()
    check('F sell -> лимит', 'SendLimit' in f.order('sell', 3, PRICE, asset=EDIT_ASSET))
    forder = f.open_order()
    check('edit чужой заявки -> 404', '404' in e.edit(forder['id'], 9, PRICE))
    check('remove чужой заявки -> 404', '404' in e.remove(forder['id']))


def scenario_saldo():
    """Задача #13: /saldo суммирует числа, а не строку (иначе всегда 0/пусто)."""
    print('[8] /saldo — агрегат контрактов')
    raw = _get('/saldo')
    check('/saldo -> 200 JSON', raw is not None and '"quant"' in raw, str(raw))
    if raw:
        rows = json.loads(raw)
        check('/saldo непустой', len(rows) >= 1 and 'quant' in rows[0], str(rows))


def scenario_market_cache():
    """Задачи #17/#19: актуальная серия и пересборка PRICE/HV/LAST/BEST/THEO.

    API уже был перезапущен (Memcached мог быть пуст) — значит значения здесь
    восстановлены из Bybit/Mongo, а не пережили рестарт сами по себе.
    """
    print('[9] Рыночный кэш (#17 серия, #19 пересборка)')
    counters = json.loads(_get('/counters/' + TICKER))
    check('PRICE доступен (Bybit/_cache)', counters[0]['price'] is not None, str(counters))
    check('HV доступен (Bybit/_cache)', counters[0]['vola'] is not None, str(counters))

    # LAST — цена последней сделки; сценарий [2]/[3] только что торговал ASSET,
    # поэтому после рестарта она обязана восстановиться из Mongo-контрактов.
    last = json.loads(_get('/last/%s/%s' % (TICKER, EXP)))
    last_price = {row['asset']: row['last'] for row in last}.get(ASSET)
    check('LAST восстановлен из Mongo', last_price == PRICE, str(last_price))

    # THEO — все страйки актуальной серии должны быть посчитаны (> 0, не null).
    theo = json.loads(_get('/theo/%s/%s' % (TICKER, EXP)))
    check('THEO посчитан для серии', len(theo) > 0 and all(
        row['theo'] is not None and row['theo'] > 0 for row in theo), str(theo[:2]))

    # BEST — структура стакана для актуальной серии (значения могут быть null).
    best = json.loads(_get('/best/%s/%s' % (TICKER, EXP)))
    check('BEST отдаёт активы серии', len(best) > 0 and 'asset' in best[0], str(best[:1]))


def scenario_health():
    """Задача #24/#25: /health отвечает 200 и сообщает о хранилищах.

    Проверяем контракт ответа при ЖИВОМ стеке: `status: ok` и все три
    хранилища `ok`. Degraded-режим (503 на данных, `status: degraded`) —
    отдельный ручной сценарий: см. docs/DONE.md (блок #20/#21/#22/#25).
    """
    print('[10] /health — состояние API и хранилищ')
    raw = _get('/health')
    check('/health -> 200 JSON', '"status"' in raw, str(raw))
    if '"status"' in raw:
        body = json.loads(raw)
        check('/health status=ok', body.get('status') == 'ok', str(body))
        storage = body.get('storage', {})
        for name in ('mongo', 'influx', 'memcached'):
            check('/health %s=ok' % name, storage.get(name) == 'ok', str(storage))


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


def scenario_market_endpoints():
    """Задача #23: публичные рыночные роуты после выноса логики в inc/state.py.

    Проверяем, что рефакторинг не сломал контракт `/state`, `/best`, `/last`,
    `/theo` (та же структура, что и «истина» из Memcached/Mongo). Значения
    BEST/THEO могут быть null, поэтому проверяем форму ответа и наличие
    активов серии.
    """
    print('[11] Рыночные роуты после #23 (state/best/last/theo)')
    state = json.loads(_get('/state'))
    check('/state содержит метки серии', len(state) > 0 and any(
        k.endswith('_TRADE') for k in state[0]), str(state[:1]))

    for path in ('/best', '/last', '/theo'):
        rows = json.loads(_get('%s/%s/%s' % (path, TICKER, EXP)))
        check('%s отдаёт активы серии' % path, len(rows) > 0 and 'asset' in rows[0], str(rows[:1]))

    theo = json.loads(_get('/theo/%s/%s' % (TICKER, EXP)))
    check('/theo: у активов есть поле theo', all('theo' in r for r in theo), str(theo[:1]))


def scenario_web_health():
    """Задача #24: /health у веб-слоя (Node) — всегда 200 + JSON.

    Отключается E2E_WEB=0, если Node-сервер не поднят (тест только против API).
    """
    if os.getenv('E2E_WEB', '1') == '0':
        print('[12] /health веб-слоя — пропущен (E2E_WEB=0)')
        return
    print('[12] /health веб-слоя (#24)')
    raw = _get_url(WEB + '/health')
    check('web /health -> 200 JSON', '"status"' in raw, str(raw)[:120])
    if '"status"' in raw:
        body = json.loads(raw)
        check('web /health status=ok', body.get('status') == 'ok', str(body))
        check('web /health видит API', body.get('api', {}).get('status') == 'ok', str(body))


def scenario_theo_targeted():
    """Задача #30: setTheo(ticker) пересчитывает только указанный тикер.

    Вызываем пересчёт напрямую (то, что делает планировщик при изменении цены)
    и проверяем, что THEO серии заполнен. Это не HTTP-контракт, а защита от
    регрессии оптимизации: сигнатура с необязательным тикером и заполнение кэша.
    """
    print('[13] setTheo(ticker) — точечный пересчёт THEO (#30)')
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'api'))
    try:
        from inc.mc import setTheo
    except ImportError as e:
        check('import inc.mc.setTheo', False, str(e))
        return
    try:
        setTheo(TICKER)
        ok = True
        err = ''
    except Exception as e:
        ok = False
        err = str(e)
    check('setTheo(TICKER) без ошибок', ok, err)
    theo = json.loads(_get('/theo/%s/%s' % (TICKER, EXP)))
    check('THEO заполнен после точечного пересчёта', len(theo) > 0 and all(
        row['theo'] is not None for row in theo), str(theo[:2]))


def scenario_frontend_assets():
    """Задачи #26/#32/#35: обновлённые ресурсы и отсутствие битой ссылки.

    Проверяем статически отданный веб-слоем контент: строгий режим в exchange.js,
    актуальную версию jQuery и отсутствие ссылки на несуществующий
    jquery-ui.css в HTML стола. Отключается E2E_WEB=0.
    """
    if os.getenv('E2E_WEB', '1') == '0':
        print('[14] фронтенд-ресурсы — пропущен (E2E_WEB=0)')
        return
    print('[14] фронтенд-ресурсы (#26 strict, #32 ссылка, #35 jQuery)')
    page = _get_url(WEB + '/exchange/eth/btc/' + EXP)
    check('стол -> 200', page.startswith('<!DOCTYPE') or 'YZoZ' in page, str(page)[:80])
    check('страница не грузит отсутствующий jquery-ui.css (#32)',
          '/stylesheets/jquery-ui.css' not in page, 'битая ссылка присутствует')
    ex = _get_url(WEB + '/javascripts/exchange.js')
    check('exchange.js в strict mode (#26)', "'use strict'" in ex, str(ex)[:80])
    jq = _get_url(WEB + '/javascripts/jquery.js')
    check('jQuery обновлён до 3.x (#35)', 'jQuery v3.' in jq, str(jq)[:80])


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
    scenario_edit()
    scenario_saldo()
    scenario_market_cache()
    scenario_health()
    scenario_market_endpoints()
    scenario_web_health()
    scenario_theo_targeted()
    scenario_frontend_assets()
    scenario_rate_limit()

    print('\nИтог: %d проверок, %d провалов' % (_checks, len(_failures)))
    if _failures:
        print('Провалено: %s' % ', '.join(_failures))
        return 1
    print('Все e2e-проверки пройдены.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
