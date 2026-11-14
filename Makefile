.PHONY: gen db engine gateway web test demo lint

PY ?= python3

gen: ## buf generate plus Python stubs
	npx buf generate
	mkdir -p engine/gen
	$(PY) -m grpc_tools.protoc -I proto --python_out=engine/gen --grpc_python_out=engine/gen --pyi_out=engine/gen proto/misconception/v1/*.proto

db: ## start postgres:16 and apply sql/schema.sql (applied on first init)
	docker compose up -d postgres

engine: ## Python gRPC server on 50051
	cd engine && $(PY) server.py

gateway: ## Go server on 8080
	cd gateway && go run .

web: ## ng serve with proxy to 8080
	cd web && npx ng serve --proxy-config proxy.conf.json

lint:
	npx buf lint

test: lint ## engine tests and buf lint
	cd engine && $(PY) -m pytest tests

demo: ## seed the default synthetic class and process it through the gateway
	@echo "TODO: implement once gateway exposes SeedSyntheticClass and ProcessClass" && exit 1
