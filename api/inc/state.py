"""Производные рыночные ответы API (задача ТЗ #23).

Чтение каталога из Memcached и сборка публичных JSON-ответов (`/state`, `/best`,
`/last`, `/theo`) вынесены из роутов `api/app.py` в этот модуль-сервис. Так
`app.py` остаётся слоем HTTP, а MEMCACHED-ключи (схема см. DEVELOPER_GUIDE §4.4)
разбираются в одном месте.

Своих соединений модуль не держит: каталог активов передаётся аргументом (его
строит bootstrap `app.py`), а чтения Memcached выполняются через переданный
getter `get`, который глушит недоступное хранилище (graceful, задача #25).
"""


def _safeGet(get, key):
    try:
        return get(key)
    except Exception:
        return None


def seriesAssets(catalog, ticker, exp):
    """Список активов серии из каталога, построенного loadCatalog().

    `catalog` — это результат inc.mc.loadCatalog(): список {ticker: {series:[...]}}.
    Возвращает список asset-строк либо [] для неизвестной серии.
    """
    for asset in catalog:
        if ticker in asset:
            for serie in asset[ticker]['series']:
                if exp in serie:
                    return serie[exp]['assets']
    return []


def getState(catalog, get, series_keys):
    """Метки изменений серий для поллинга столом (GET /state)."""
    out = []
    for serie in series_keys:
        out.append({
            serie + '_TRADE': str(_safeGet(get, 'STATE_' + serie + '_TRADE')),
            serie + '_ORDER': str(_safeGet(get, 'STATE_' + serie + '_ORDER')),
        })
    return out


def getBest(catalog, get, ticker, exp):
    """Лучшие bid/ask по всем активам серии (GET /best)."""
    assets = seriesAssets(catalog, ticker, exp)
    out = []
    for asset in assets:
        out.append({'asset': asset, 'type': 'sell', 'price': _safeGet(get, 'BEST_SELL_' + asset)})
    for asset in assets:
        out.append({'asset': asset, 'type': 'buy', 'price': _safeGet(get, 'BEST_BUY_' + asset)})
    return out


def getLast(catalog, get, ticker, exp):
    """Цены последних сделок по активам серии (GET /last)."""
    assets = seriesAssets(catalog, ticker, exp)
    out = []
    for asset in assets:
        price = _safeGet(get, 'LAST_' + asset)
        if price is not None:
            out.append({'asset': asset, 'last': price})
    return out


def getTheo(catalog, get, ticker, exp):
    """Теоретические цены по активам серии (GET /theo)."""
    assets = seriesAssets(catalog, ticker, exp)
    out = []
    for asset in assets:
        out.append({'asset': asset, 'theo': _safeGet(get, 'THEO_' + asset)})
    return out
