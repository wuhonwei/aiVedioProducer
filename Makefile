.PHONY: install-backend install-frontend install check-env \
	dev-backend dev-frontend test-backend test-frontend test

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

install-backend:
	cd $(ROOT)backend && pip install -e ".[dev]"

install-frontend:
	cd $(ROOT)frontend && npm ci

install: install-backend install-frontend

check-env:
	@$(ROOT)scripts/check-env.sh

dev-backend:
	cd $(ROOT)backend && uvicorn aivp.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000

dev-frontend:
	cd $(ROOT)frontend && npm run dev -- --host 127.0.0.1 --port 5173

test-backend:
	cd $(ROOT)backend && python -m pytest -v

test-frontend:
	cd $(ROOT)frontend && npm test

test: test-backend test-frontend
