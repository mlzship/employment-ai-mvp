.PHONY: install test lint run docker-build docker-up docker-down

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check src tests scripts/remote_golden_flow.py
	ruff format --check src tests scripts/remote_golden_flow.py

run:
	uvicorn employment_ai.main:app --reload --host 0.0.0.0 --port 8000

docker-build:
	docker build -t employment-ai-mvp:local .

docker-up:
	docker compose up --build

docker-down:
	docker compose down
