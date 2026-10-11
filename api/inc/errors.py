class ExchangeError(Exception):
    """Доменная ошибка с HTTP-кодом.

    Нужна, чтобы бизнес-логика (`inc/*`) не тянула Bottle, но могла сообщить
    роуту `api/app.py` осмысленный код и текст, который будет отдан единым
    JSON-форматом ошибки (задача ТЗ #16).
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class StorageError(ExchangeError):
    """Хранилище недоступно (Mongo/Influx/Memcached) — задача ТЗ #25.

    Отдаётся клиенту как 503 с понятным текстом, вместо невнятного 500 или
    падения импорта. Это осознанно внешняя (а не доменная) ошибка, поэтому
    вынесена в отдельный подкласс.
    """

    def __init__(self, message):
        super().__init__(503, message)
