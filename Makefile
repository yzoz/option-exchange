# YZoZ Option Exchange — единые команды разработки (задача ТЗ #21).
#
# `make up` поднимает хранилища + Node-веб + Python API/планировщик как
# локальные процессы (как в RUNBOOK). `make docker-up` поднимает весь стек
# целиком в контейнерах (compose-профиль «app»). `make help` — список целей.

SHELL := /bin/bash
API_URL ?= http://localhost:6969
API_LOG ?= /tmp/opencode/oe-api.log
THEO_LOG ?= /tmp/opencode/oe-theo.log
WEB_LOG ?= /tmp/opencode/oe-web.log

.PHONY: help env storage up down logs e2e test check docker-up docker-down docker-logs

help: ## Показать этот список
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: ## Создать .env из .env.example (если ещё нет)
	@[ -f .env ] || (cp .env.example .env && echo "создан .env")

storage: env ## Поднять только хранилища (Mongo + Memcached + InfluxDB)
	docker compose up -d

up: storage ## Поднять весь стек локально (хранилища + API + theo + веб)
	@[ -d .venv ] || (python3 -m venv .venv && .venv/bin/pip -q install -r requirements.txt)
	@[ -d node_modules ] || npm install
	@mkdir -p /tmp/opencode
	@setsid nohup env PY_MODE=dev .venv/bin/python api/app.py >$(API_LOG) 2>&1 </dev/null & echo "API   -> $(API_LOG)"
	@setsid nohup env PY_MODE=dev .venv/bin/python api/theo.py >$(THEO_LOG) 2>&1 </dev/null & echo "theo  -> $(THEO_LOG)"
	@setsid nohup node ./bin/www >$(WEB_LOG) 2>&1 </dev/null & echo "web   -> $(WEB_LOG)"
	@sleep 3
	@echo "готово:  api http://localhost:6969/health   web http://localhost:3000/exchange/"

down: ## Остановить локальные процессы
	-pkill -f "api/app.py"
	-pkill -f "api/theo.py"
	-pkill -f "bin/www"

logs: ## Хвосты логов локальных процессов
	@tail -n 40 -f $(API_LOG) $(THEO_LOG) $(WEB_LOG)

e2e: ## Прогнать e2e (при поднятом API)
	.venv/bin/python tests/e2e.py

test: e2e ## Псевдоним для e2e

check: ## Быстрые проверки синтаксиса (Python + JS) и конфиг compose
	.venv/bin/python -m py_compile api/app.py api/theo.py api/inc/*.py tools/mongotest.py tests/e2e.py
	node --check app.js && node --check bin/www && node --check routes/*.js && node --check lib/*.js && node --check public/javascripts/exchange.js
	docker compose config --quiet
	@echo "check: ok"

docker-up: env ## Поднять весь стек в контейнерах (compose-профиль app)
	docker compose --profile app up -d --build

docker-down: ## Остановить контейнерный стек
	docker compose --profile app down

docker-logs: ## Логи контейнеров
	docker compose --profile app logs -f --tail=100
