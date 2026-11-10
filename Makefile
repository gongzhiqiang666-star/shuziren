.PHONY: web build test test-workers test-browser test-live-readiness test-v122-proof build-v122-proof check-live-readiness-example doctor up down

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

test-v122-proof:
	python3 -m unittest scripts/test_v122_proof.py -v

build-v122-proof:
	@test -n "$(V122_RUNTIME_SOURCE)" || (echo "V122_RUNTIME_SOURCE is required"; exit 2)
	@test -n "$(V122_PROOF_DESTINATION)" || (echo "V122_PROOF_DESTINATION is required"; exit 2)
	python3 scripts/build_v122_proof.py --runtime-source "$(V122_RUNTIME_SOURCE)" --destination "$(V122_PROOF_DESTINATION)"

check-live-readiness-example:
	python3 scripts/live_readiness.py check-assets --manifest config/live-readiness.example.json --output test-results/live-readiness/example-assets.json

doctor:
	python3 scripts/doctor.py

up:
	sh scripts/start-local.sh

down:
	docker compose down
