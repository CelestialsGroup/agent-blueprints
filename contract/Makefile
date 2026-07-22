.PHONY: bootstrap-contracts prepare-openapi validate-static validate-contracts validate-compatibility \
	validate-jcs validate-supply-chain validate-contract validate-architecture bundle-openapi \
	validate-bundle-determinism validate-all clean-contracts

PYTHON ?= .venv/bin/python
PNPM ?= corepack pnpm
COREPACK_HOME ?= $(CURDIR)/.venv/corepack-cache
export COREPACK_HOME

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

validate-contract: validate-static validate-contracts validate-compatibility validate-jcs validate-bundle-determinism
	$(PYTHON) scripts/verify_contract_manifest.py
	node scripts/verify_contract_manifest.mjs
	$(PYTHON) scripts/generate_validation_evidence.py
	@echo "Contract, semantic, compatibility-comparator, JCS and OpenAPI gates passed."

validate-architecture: validate-contract
	@echo "validate-architecture is a compatibility alias; use validate-contract."

validate-all:
	./scripts/validate_all.sh
	$(MAKE) bundle-openapi

clean-contracts:
	rm -rf .venv node_modules build
