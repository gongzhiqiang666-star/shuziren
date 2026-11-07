.PHONY: web build test test-workers test-browser test-live-readiness check-live-readiness-example doctor up down

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

test-live-readiness:
	python3 -m unittest scripts/test_live_readiness.py -v

check-live-readiness-example:
	python3 scripts/live_readiness.py check-assets --manifest config/live-readiness.example.json --output test-results/live-readiness/example-assets.json

doctor:
	python3 scripts/doctor.py

up:
	sh scripts/start-local.sh

down:
	docker compose down
