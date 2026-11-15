.PHONY: init up dev frontend-build test integration migrations-check readonly-check stats-check simulate deploy
init:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv sync --project services/python --frozen
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/init-env.py
up: init
	docker compose up -d --build
dev: init frontend-build
	docker compose -f compose.yaml -f compose.dev.yaml up -d --build
frontend-build:
	npm ci --prefix frontend --no-audit --no-fund
	npm --prefix frontend run build
test: frontend-build
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python pytest services/python/tests -q
	npm --prefix frontend test
	node --test .github/scripts/*.test.cjs
	node --check frontend/dist/ride/sw.js
integration:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/integration.py
migrations-check:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/check-migrations.py
readonly-check:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/readonly-check.py
stats-check:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/stats-check.py
simulate:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/simulate.py $(SIM_ARGS)
deploy:
	bash scripts/bootstrap-deploy.sh
