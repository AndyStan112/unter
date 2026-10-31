.PHONY: init up dev test integration migrations-check deploy
init:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv sync --project services/python --frozen
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/init-env.py
up: init
	docker compose up -d --build
dev: init
	docker compose -f compose.yaml -f compose.dev.yaml up -d --build
test:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python pytest services/python/tests -q
	node --test .github/scripts/*.test.cjs
	node --check web/app.js
	node --check web/sw.js
integration:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/integration.py
migrations-check:
	UV_CACHE_DIR=/tmp/unter-uv-cache uv run --project services/python python scripts/check-migrations.py
deploy:
	bash scripts/bootstrap-deploy.sh
