COMPOSE ?= docker compose

-include .env
export

.PHONY: build up down logs ps config health deploy

build:
	$(COMPOSE) -f docker-compose.yml build

up:
	$(COMPOSE) -f docker-compose.yml up -d

down:
	$(COMPOSE) -f docker-compose.yml down

logs:
	$(COMPOSE) -f docker-compose.yml logs -f

ps:
	$(COMPOSE) -f docker-compose.yml ps

config:
	$(COMPOSE) -f docker-compose.yml config

health:
	curl -fsS http://127.0.0.1:$${GPTSOVITS_GATEWAY_PORT:-7088}/healthz
	curl -fsS http://127.0.0.1:$${GPTSOVITS_FRONTEND_PORT:-7070}/nginx-healthz

deploy:
	bash scripts/deploy.sh
