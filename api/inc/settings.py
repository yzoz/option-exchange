import os

from dotenv import load_dotenv
from influxdb import InfluxDBClient
from pymongo import MongoClient
from memcache import Client as MemClient

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


def indb(inDB):
    return InfluxDBClient(InHost, inPort, inUser, inPwd, inDB)


# --- MongoDB ---
moUser = _env('MONGO_USER', '')
moPwd = _env('MONGO_PASSWORD', '')
moHost = _env('MONGO_HOST', 'localhost')
moPort = _env('MONGO_PORT', '27017')
moDB = _env('MONGO_DB', 'exchange')


def modb():
    uri = 'mongodb://%s:%s@%s:%s/?authSource=admin' % (moUser, moPwd, moHost, moPort)
    cli = MongoClient(uri)
    return cli[moDB]


# --- Memcached ---
mcHost = _env('MEMCACHED_HOST', '127.0.0.1')
mcPort = _env('MEMCACHED_PORT', '11211')


def memdb():
    return MemClient(['%s:%s' % (mcHost, mcPort)], debug=0)


# --- Пути к данным репозитория (не зависят от текущего каталога) ---
ROOT = _ROOT
INSTRUMENTS = os.path.join(_ROOT, 'exchange', 'instruments.json')
CACHE_DIR = os.path.join(_ROOT, '_cache')
