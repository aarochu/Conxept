.PHONY: gen db engine gateway web test demo lint eval test-gateway web-build rehearse
.PHONY: gen db engine gateway web test demo lint eval test-gateway web-build real-eval
.PHONY: gen db engine gateway web test demo lint eval test-gateway web-build baseline

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

gateway: ## Go server on 8080, serving the built web app (make web-build)
	cd gateway && WEB_DIR=$${WEB_DIR:-../web/dist/web/browser} go run .

web: ## ng serve on 4200 with proxy to 8080
	cd web && npx ng serve

web-build: ## production build into web/dist/web/browser (served by the gateway)
	cd web && npx ng build

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

.PHONY: acceptance
acceptance: ## fail on unmet spec 8.2 synthetic accuracy and latency targets
	cd engine && $(PY) acceptance.py --out acceptance_out/report.json

rehearse: ## demo script 3 times from a clean local database (deletes local data; needs engine + gateway running)
	cd gateway && go run ./cmd/rehearse -reset -runs 3
SPLIT ?= test
.PHONY: real-check
real-check: ## check collection metadata without diagnosing held-out derivations
	cd engine && $(PY) real_eval.py ../data/real/derivations.csv --split all --check

.PHONY: worksheet
worksheet: ## generate the anonymous eight-problem real-data collection sheet
	cd engine && $(PY) worksheet.py

real-eval: ## engine on hand-labelled real derivations, spec 8.4 (data/real/derivations.csv)
	cd engine && $(PY) real_eval.py ../data/real/derivations.csv --split $(SPLIT)
baseline: ## model-only baseline, spec 8.5 (calls the Claude API ~200 times; costs money)
	cd engine && $(PY) baseline.py --out baseline_out
