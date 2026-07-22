.PHONY: bootstrap-contracts prepare-openapi validate-static validate-contracts validate-compatibility \
	validate-jcs validate-supply-chain validate-architecture bundle-openapi \
	validate-bundle-determinism validate-all clean-contracts

PYTHON ?= .venv/bin/python
PNPM ?= corepack pnpm

bootstrap-contracts:
	./scripts/bootstrap_contracts.sh

prepare-openapi:
	$(PYTHON) scripts/prepare_openapi.py

validate-supply-chain:
	$(PYTHON) scripts/check_supply_chain.py

validate-static:
	$(PYTHON) scripts/offline_static_audit.py

validate-jcs:
	$(PYTHON) scripts/jcs/verify_python.py
	node scripts/jcs/verify_node.mjs
	test -z "$$(gofmt -l scripts/jcs/go/*.go)"
	cd scripts/jcs/go && go test ./...

validate-compatibility:
	$(PYTHON) scripts/check_contract_compatibility.py

validate-contracts: prepare-openapi
	$(PYTHON) scripts/validate_contracts.py
	$(PYTHON) scripts/validate_semantics.py
	node scripts/lint_openapi_zero.mjs

bundle-openapi: prepare-openapi
	mkdir -p build
	$(PNPM) run bundle:openapi

validate-bundle-determinism: prepare-openapi
	$(PYTHON) scripts/verify_openapi_bundle_determinism.py

validate-architecture: validate-static validate-contracts validate-compatibility validate-jcs validate-bundle-determinism
	$(PYTHON) scripts/verify_contract_manifest.py
	node scripts/verify_contract_manifest.mjs
	$(PYTHON) scripts/generate_validation_evidence.py
	@echo "Architecture contract, semantic, compatibility-comparator, JCS and OpenAPI gates passed."

validate-all:
	./scripts/validate_all.sh
	$(MAKE) bundle-openapi

clean-contracts:
	rm -rf .venv node_modules build
