#!/usr/bin/env python3
"""Планировщик рыночных расчётов YZoZ (отдельный сервис).

Отвечает за обновление производных рыночных данных в Memcached, которые фронт
показывает на торговом столе:

  * ``PRICE_<TICKER>``  — цена базового актива (Bybit или ``_cache``);
  * ``HV_<TICKER>``     — годовая историческая волатильность (Bybit);
  * ``THEO_<ASSET>``    — теоретическая цена по Блэку–Шоулзу;
  * ``LAST_<ASSET>``    — цена последней сделки (из Mongo contracts);
  * ``BEST_<SIDE>_<ASSET>`` — лучшие цены стакана (из Mongo orders).

Почему это отдельный процесс (задача ТЗ #18): пересчёт не должен блокировать
HTTP-API и должен продолжать работать между запросами. Он **не** держит
собственные данные — источник истины для цен это Bybit, для контрактов/заявок
MongoDB; Memcached лишь кэширует посчитанное.

Запуск (из корня репозитория, рядом с API):

    setsid nohup env PY_MODE=dev python api/theo.py >/tmp/opencode/oe-theo.log 2>&1 </dev/null &
    # один прогон пересчёта (без цикла) — удобно для отладки/CI:
    PY_MODE=dev python api/theo.py --once
"""

import os
import sys
import time
import schedule

# Позволяем запускать и как `python api/theo.py`, и как модуль: inc.* ищется
# относительно каталога api/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inc.mc import loadCatalog, rebuildCache, setCurrent, setHV, setTheo, getTickers, _mcGet
from inc.settings import storageStatus, formatStorageStatus

HV_INTERVAL_MIN = 15

# Последняя цена, по которой для тикера считался THEO. Позволяет не гонять
# полный пересчёт Блэка-Шоулза, если цена не изменилась (задача ТЗ #30).
_lastPrice = {}


def warn_storage(stage):
    """Напечатать состояние хранилищ; не падать, если что-то недоступно (#25)."""
    status = storageStatus(force=True)
    if any(status.values()):
        print('[theo] %s: хранилища — %s' % (stage, formatStorageStatus(status)), flush=True)
    return status


def tick():
    """Ежеминутный пересчёт цены и теоретических цен.

    THEO пересчитывается только для тикеров, у которых цена изменилась с
    прошлого тика (задача ТЗ #30). Сам пересчёт нужен и после смены HV —
    вызывающий сбрасывает историю цен при обновлении волатильности.
    """
    try:
        prices = setCurrent() or {}
        changed = []
        for ticker in (getTickers() or []):
            price = prices.get(ticker, _mcGet('PRICE_' + ticker))
            if price != _lastPrice.get(ticker):
                setTheo(ticker)
                _lastPrice[ticker] = price
                changed.append(ticker)
        print('[theo] %s: PRICE обновлён, THEO пересчитан (%s)'
              % (time.strftime('%Y-%m-%d %H:%M:%S'), ', '.join(changed) or 'без изменений'),
              flush=True)
    except Exception as e:
        # Разовая ошибка (например, мигнул Memcached/Mongo) не должна убивать
        # долгоживущий процесс — следующий тик попробует снова (задача #25).
        print('[theo] tick пропущен: %s' % e, flush=True)


def refreshHV():
    """Обновить волатильность и заставить пересчитать THEO на следующем тике.

    После смены HV прежний THEO перестаёт быть верным, поэтому сбрасываем
    историю цен — ближайший tick() пересчитает THEO для всех тикеров.
    """
    setHV()
    _lastPrice.clear()


def rebuild():
    """Полная пересборка кэша: каталог + PRICE/HV/LAST/BEST/THEO."""
    print('[theo] старт: пересборка каталога и рыночного кэша', flush=True)
    warn_storage('старт')
    loadCatalog()
    rebuildCache()
    _lastPrice.clear()
    print('[theo] кэш пересобран', flush=True)


def main():
    if '--once' in sys.argv:
        rebuild()
        return 0
    rebuild()
    schedule.every(1).minutes.do(tick)
    schedule.every(HV_INTERVAL_MIN).minutes.do(refreshHV)
    print('[theo] планировщик запущен: PRICE/THEO — 1 мин, HV — %d мин' % HV_INTERVAL_MIN,
          flush=True)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    sys.exit(main())
