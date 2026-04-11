COMPOSE ?= docker compose
SERVICE_COMPOSE ?= docker compose
PYTHON ?= python3
UVICORN ?= uvicorn

-include .env
export

.PHONY: up down build logs ps config check health e2e e2e-full live-profile \
        gateway render live preprocess finetune-api finetune-manual \
        render-up render-down render-logs render-build render-health \
        live-up live-down live-logs live-build live-health \
        preprocess-up preprocess-down preprocess-logs preprocess-build preprocess-health \
        finetune-up finetune-down finetune-logs finetune-build finetune-health \
        gateway-up gateway-down gateway-logs gateway-build gateway-health \
        frontend-up frontend-down frontend-logs frontend-build frontend-health \
        render-stack-up render-stack-down render-stack-logs render-stack-build render-stack-health render-stack-ps render-stack-deploy

up:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

config:
	$(COMPOSE) config

check:
	PYTHONPYCACHEPREFIX=/tmp/fish-speech-pycache $(PYTHON) -m py_compile $$(find shared -name '*.py') $$(find services -path '*/app/*.py' -o -path '*/app/*/*.py') tests/e2e/test_services.py tests/e2e/profile_live.py
	bash -n services/api-gateway/entrypoint.sh services/tts-render/entrypoint.sh services/tts-live/entrypoint.sh services/text-preprocess/entrypoint.sh services/finetune/entrypoint.sh services/finetune/fine_tune_runner.sh services/finetune/manual/entrypoint.sh scripts/deploy-render-stack.sh
	$(COMPOSE) config >/dev/null
	for f in compose/render.yml compose/live.yml compose/preprocess.yml compose/finetune-api.yml compose/gateway.yml compose/frontend.yml compose/render-stack.yml; do docker compose -f $$f config >/dev/null; done

health:
	curl -fsS http://127.0.0.1:$${GATEWAY_PORT:-7777}/healthz
	curl -fsS http://127.0.0.1:$${RENDER_PORT:-7778}/healthz
	curl -fsS http://127.0.0.1:$${LIVE_PORT:-7779}/healthz
	curl -fsS http://127.0.0.1:$${PREPROCESS_PORT:-7780}/healthz
	curl -fsS http://127.0.0.1:$${FINETUNE_PORT:-7781}/healthz

e2e:
	$(PYTHON) -m unittest discover -s tests/e2e -p 'test_*.py' -v

e2e-full:
	E2E_TTS=1 $(PYTHON) -m unittest discover -s tests/e2e -p 'test_*.py' -v

live-profile:
	$(PYTHON) tests/e2e/profile_live.py --target gateway --host $${E2E_HOST:-127.0.0.1} --port $${GATEWAY_PORT:-7777}

render-build:
	$(SERVICE_COMPOSE) -f compose/render.yml build

render-up:
	$(SERVICE_COMPOSE) -f compose/render.yml up -d

render-down:
	$(SERVICE_COMPOSE) -f compose/render.yml down

render-logs:
	$(SERVICE_COMPOSE) -f compose/render.yml logs -f

render-health:
	curl -fsS http://127.0.0.1:$${RENDER_PORT:-7778}/healthz

live-build:
	$(SERVICE_COMPOSE) -f compose/live.yml build

live-up:
	$(SERVICE_COMPOSE) -f compose/live.yml up -d

live-down:
	$(SERVICE_COMPOSE) -f compose/live.yml down

live-logs:
	$(SERVICE_COMPOSE) -f compose/live.yml logs -f

live-health:
	curl -fsS http://127.0.0.1:$${LIVE_PORT:-7779}/healthz

preprocess-build:
	$(SERVICE_COMPOSE) -f compose/preprocess.yml build

preprocess-up:
	$(SERVICE_COMPOSE) -f compose/preprocess.yml up -d

preprocess-down:
	$(SERVICE_COMPOSE) -f compose/preprocess.yml down

preprocess-logs:
	$(SERVICE_COMPOSE) -f compose/preprocess.yml logs -f

preprocess-health:
	curl -fsS http://127.0.0.1:$${PREPROCESS_PORT:-7780}/healthz

finetune-build:
	$(SERVICE_COMPOSE) -f compose/finetune-api.yml build

finetune-up:
	$(SERVICE_COMPOSE) -f compose/finetune-api.yml up -d

finetune-down:
	$(SERVICE_COMPOSE) -f compose/finetune-api.yml down

finetune-logs:
	$(SERVICE_COMPOSE) -f compose/finetune-api.yml logs -f

finetune-health:
	curl -fsS http://127.0.0.1:$${FINETUNE_PORT:-7781}/healthz

gateway-build:
	$(SERVICE_COMPOSE) -f compose/gateway.yml build

gateway-up:
	$(SERVICE_COMPOSE) -f compose/gateway.yml up -d

gateway-down:
	$(SERVICE_COMPOSE) -f compose/gateway.yml down

gateway-logs:
	$(SERVICE_COMPOSE) -f compose/gateway.yml logs -f

gateway-health:
	curl -fsS http://127.0.0.1:$${GATEWAY_PORT:-7777}/healthz

frontend-build:
	$(SERVICE_COMPOSE) -f compose/frontend.yml build

frontend-up:
	$(SERVICE_COMPOSE) -f compose/frontend.yml up -d

frontend-down:
	$(SERVICE_COMPOSE) -f compose/frontend.yml down

frontend-logs:
	$(SERVICE_COMPOSE) -f compose/frontend.yml logs -f

frontend-health:
	curl -fsS http://127.0.0.1:$${FRONTEND_PORT:-7070}/nginx-healthz

render-stack-build:
	$(SERVICE_COMPOSE) -f compose/render-stack.yml build

render-stack-up:
	$(SERVICE_COMPOSE) -f compose/render-stack.yml up -d

render-stack-down:
	$(SERVICE_COMPOSE) -f compose/render-stack.yml down

render-stack-logs:
	$(SERVICE_COMPOSE) -f compose/render-stack.yml logs -f

render-stack-health:
	curl -fsS http://127.0.0.1:$${GATEWAY_PORT:-7777}/healthz
	curl -fsS http://127.0.0.1:$${RENDER_PORT:-7778}/healthz
	curl -fsS http://127.0.0.1:$${PREPROCESS_PORT:-7780}/healthz
	curl -fsS http://127.0.0.1:$${FINETUNE_PORT:-7781}/healthz
	curl -fsS http://127.0.0.1:$${FRONTEND_PORT:-7070}/nginx-healthz

render-stack-ps:
	$(SERVICE_COMPOSE) -f compose/render-stack.yml ps

render-stack-deploy:
	bash scripts/deploy-render-stack.sh

gateway:
	PYTHONPATH=$$(pwd) $(UVICORN) app.main:app --app-dir services/api-gateway --host 0.0.0.0 --port $${GATEWAY_PORT:-7777}

render:
	PYTHONPATH=$$(pwd) $(UVICORN) app.main:app --app-dir services/tts-render --host 0.0.0.0 --port $${RENDER_PORT:-7778}

live:
	PYTHONPATH=$$(pwd) $(UVICORN) app.main:app --app-dir services/tts-live --host 0.0.0.0 --port $${LIVE_PORT:-7779}

preprocess:
	PYTHONPATH=$$(pwd) $(UVICORN) app.main:app --app-dir services/text-preprocess --host 0.0.0.0 --port $${PREPROCESS_PORT:-7780}

finetune-api:
	PYTHONPATH=$$(pwd) $(UVICORN) app.main:app --app-dir services/finetune --host 0.0.0.0 --port $${FINETUNE_PORT:-7781}

finetune-manual:
	$(COMPOSE) --profile manual run --rm finetune
