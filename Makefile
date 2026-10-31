.PHONY: web build test test-workers test-browser doctor up down

web:
	cd web && npm ci && npm run build

build: web
	mkdir -p build
	cd server && go build -trimpath -o ../build/shuziren ./cmd/server

test:
	cd server && go test -race ./... && go vet ./...
	cd web && npm test && npm run build

test-workers:
	python3 -m pytest workers/tts workers/retrieval scripts/test_local_tools.py -q

test-browser:
	npm --prefix tests/browser test

doctor:
	python3 scripts/doctor.py

up:
	sh scripts/start-local.sh

down:
	docker compose down
