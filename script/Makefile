.PHONY: bootstrap-contracts prepare-openapi validate-static validate-contracts validate-compatibility \
	validate-jcs validate-supply-chain validate-contract validate-architecture bundle-openapi \
	validate-bundle-determinism validate-all clean-contracts

SCRIPT_ROOT := $(abspath $(CURDIR))
AGENT_PLATFORM_CONTRACT_ROOT ?= $(abspath $(SCRIPT_ROOT)/../contract)
AGENT_PLATFORM_BLUEPRINT_ROOT ?= $(abspath $(SCRIPT_ROOT)/../blueprint)
PYTHON ?= .venv/bin/python
PNPM ?= corepack pnpm
COREPACK_HOME ?= $(CURDIR)/.venv/corepack-cache
export COREPACK_HOME
export AGENT_PLATFORM_CONTRACT_ROOT
export AGENT_PLATFORM_BLUEPRINT_ROOT

bootstrap-contracts:
	./contract/bootstrap.sh

prepare-openapi:
	$(PYTHON) contract/validation/prepare_openapi.py

validate-supply-chain:
	$(PYTHON) contract/validation/check_supply_chain.py

validate-static:
	$(PYTHON) contract/validation/offline_static_audit.py

validate-jcs:
	$(PYTHON) contract/jcs/verify_python.py
	node contract/jcs/verify_node.mjs
	test -z "$$(gofmt -l contract/jcs/go/*.go)"
	cd contract/jcs/go && go test ./...

validate-compatibility:
	$(PYTHON) contract/compatibility/check_contract_compatibility.py

validate-contracts: prepare-openapi
	$(PYTHON) contract/validation/validate_contracts.py
	$(PYTHON) contract/validation/validate_semantics.py
	node contract/validation/lint_openapi_zero.mjs

bundle-openapi: prepare-openapi
	mkdir -p build
	$(PNPM) run bundle:openapi

validate-bundle-determinism: prepare-openapi
	$(PYTHON) contract/validation/verify_openapi_bundle_determinism.py

validate-contract: validate-static validate-contracts validate-compatibility validate-jcs validate-bundle-determinism
	$(PYTHON) contract/manifest/verify_contract_manifest.py
	node contract/manifest/verify_contract_manifest.mjs
	$(PYTHON) contract/validation/generate_validation_evidence.py
	@echo "Contract, semantic, compatibility-comparator, JCS and OpenAPI gates passed."

validate-architecture: validate-contract
	@echo "validate-architecture is a compatibility alias; use validate-contract."

validate-all:
	./contract/validate.sh
	$(MAKE) bundle-openapi

clean-contracts:
	rm -rf .venv node_modules build
