.PHONY: web build test up down

web:
	cd web && npm ci && npm run build

build: web
	mkdir -p build
	cd server && go build -trimpath -o ../build/shuziren ./cmd/server

test:
	cd server && go test ./...
	cd web && npm test && npm run build

up:
	sh scripts/start-local.sh

down:
	docker compose down
