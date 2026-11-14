.PHONY: gen db engine gateway web test demo lint eval test-gateway

PY ?= $(CURDIR)/.venv/bin/python

gen: ## buf generate plus Python stubs
	PATH="$$(go env GOPATH)/bin:$$PATH" npx buf generate
	cp sql/queries.sql gateway/queries.sql
	mkdir -p engine/gen
	$(PY) -m grpc_tools.protoc -I proto --python_out=engine/gen --grpc_python_out=engine/gen --pyi_out=engine/gen proto/misconception/v1/*.proto

db: ## start postgres:16 and apply sql/schema.sql (docker, else local postgresql@16)
	./scripts/dev-db.sh

engine: ## Python gRPC server on 50051
	cd engine && $(PY) server.py

gateway: ## Go server on 8080
	cd gateway && go run .

web: ## ng serve with proxy to 8080
	cd web && npx ng serve --proxy-config proxy.conf.json

lint:
	npx buf lint

test: lint ## engine tests and buf lint
	cd engine && $(PY) -m pytest

demo: ## seed the default synthetic class and process it through the gateway
	cd gateway && go run ./cmd/demo

test-gateway: ## gateway tests against a running engine and Postgres
	cd gateway && ENGINE_ADDR=$${ENGINE_ADDR:-localhost:50051} DATABASE_URL=$${DATABASE_URL:-postgres://postgres:postgres@localhost:5432/misconception} go test -count=1 ./...

eval: ## engine-only evaluation on a seeded synthetic class
	cd engine && $(PY) evaluate.py 60 7
