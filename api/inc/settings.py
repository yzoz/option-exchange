import atexit
import os
import threading
import time

from dotenv import load_dotenv
from influxdb import InfluxDBClient
from memcache import Client as MemClient
from pymongo import MongoClient

# Загружаем .env из корня репозитория (api/inc/ -> ../../.env).
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
load_dotenv(os.path.join(_ROOT, '.env'))


def _env(name, default=None):
    return os.getenv(name, default)


# --- InfluxDB 1.x ---
InHost = _env('INFLUX_HOST', 'localhost')
inPort = int(_env('INFLUX_PORT', '8086'))
inUser = _env('INFLUX_USER', '')
inPwd = _env('INFLUX_PASSWORD', '')
inTimeout = float(_env('INFLUX_TIMEOUT', '2'))


def indb(inDB='spot'):
    return InfluxDBClient(InHost, inPort, inUser, inPwd, inDB, timeout=inTimeout)


# --- MongoDB ---
moUser = _env('MONGO_USER', '')
moPwd = _env('MONGO_PASSWORD', '')
moHost = _env('MONGO_HOST', 'localhost')
moPort = _env('MONGO_PORT', '27017')
moDB = _env('MONGO_DB', 'exchange')
# Таймаут выбора сервера: чтобы недоступный Mongo падал за секунды, а не за 30 с.
moSelectTimeout = int(_env('MONGO_SELECT_TIMEOUT', '2000'))

if moUser and moPwd:
    _moUri = 'mongodb://%s:%s@%s:%s/?authSource=admin' % (moUser, moPwd, moHost, moPort)
else:
    _moUri = 'mongodb://%s:%s/' % (moHost, moPort)

_moClient = None
_moClientLock = threading.Lock()
_moDatabases = {}


def _getMoClient():
    """Единый ленивый MongoClient на процесс.

    Конструктор ничего не делает по сети — именно поэтому импорт приложения
    не падает при недоступном Mongo (задача ТЗ #25). Соединение/ошибка
    проявляются на первой операции; их перехватывают проверки доступности.
    """
    global _moClient
    if _moClient is None:
        with _moClientLock:
            if _moClient is None:
                cli = MongoClient(_moUri, serverSelectionTimeoutMS=moSelectTimeout)
                atexit.register(cli.close)
                _moClient = cli
    return _moClient


def modb(name=None):
    name = name or moDB
    db = _moDatabases.get(name)
    if db is None:
        db = _getMoClient()[name]
        _moDatabases[name] = db
    return db


# --- Memcached ---
mcHost = _env('MEMCACHED_HOST', '127.0.0.1')
mcPort = _env('MEMCACHED_PORT', '11211')

_mcClient = None
_mcClientLock = threading.Lock()


def memdb():
    """Единый Memcached-клиент на процесс (возвращается тем же, что и раньше).

    `python-memcached` соединяется лениво, поэтому создание клиента безопасно
    при недоступном Memcached.
    """
    global _mcClient
    if _mcClient is None:
        with _mcClientLock:
            if _mcClient is None:
                _mcClient = MemClient(['%s:%s' % (mcHost, mcPort)], debug=0)
    return _mcClient


# --- Проверка доступности хранилищ (graceful-поведение, задача ТЗ #25) ---
# Каждый пробник возвращает строку с ошибкой либо None (всё хорошо). Результат
# кэшируется на STORAGE_PROBE_TTL секунд, чтобы не бить по хранилищам на каждый
# запрос; force=True заставляет проверить заново.
STORAGE_PROBE_TTL = float(_env('STORAGE_PROBE_TTL', '10'))
_probe = {}
_probeLock = threading.Lock()


def _cachedProbe(name, fn, force=False):
    now = time.time()
    with _probeLock:
        rec = _probe.get(name)
        if rec and not force and now - rec[0] < STORAGE_PROBE_TTL:
            return rec[1]
    err = fn()
    with _probeLock:
        _probe[name] = (now, err)
    return err


def _probeMongo():
    try:
        _getMoClient().admin.command('ping')
        return None
    except Exception as e:
        return str(e)


def _probeInflux():
    try:
        indb('spot').ping()
        return None
    except Exception as e:
        return str(e)


def _probeMemcached():
    try:
        if memdb().get_stats():
            return None
        return 'нет ответа от Memcached'
    except Exception as e:
        return str(e)


def mongoError(force=False):
    """None, если Mongo доступен; иначе текст ошибки."""
    return _cachedProbe('mongo', _probeMongo, force)


def influxError(force=False):
    """None, если InfluxDB доступен; иначе текст ошибки."""
    return _cachedProbe('influx', _probeInflux, force)


def memcachedError(force=False):
    """None, если Memcached доступен; иначе текст ошибки."""
    return _cachedProbe('memcached', _probeMemcached, force)


def storageStatus(force=False):
    """Карта {имя: ошибка|None} по всем трём хранилищам."""
    return {
        'mongo': mongoError(force),
        'influx': influxError(force),
        'memcached': memcachedError(force),
    }


def formatStorageStatus(status):
    parts = []
    for name, err in status.items():
        parts.append('%s: %s' % (name, 'ok' if err is None else 'DOWN (%s)' % err))
    return '; '.join(parts)


# --- Пути к данным репозитория (не зависят от текущего каталога) ---
ROOT = _ROOT
INSTRUMENTS = os.path.join(_ROOT, 'exchange', 'instruments.json')
CACHE_DIR = os.path.join(_ROOT, '_cache')
