# Python API + планировщик (Bottle, api/app.py и api/theo.py).
# Образ используется compose-профилем «app» (полный стек в контейнерах).
FROM python:3.10-slim

WORKDIR /app

# Сборка некоторых зависимостей (pymongo/influxdb) может требовать компилятора.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Порт по умолчанию (внутри compose переопределяется на 6969).
EXPOSE 6969
CMD ["python", "api/app.py"]
