.PHONY: bootstrap-contracts prepare-openapi validate-contracts validate-compatibility \
	validate-jcs validate-supply-chain bundle-openapi validate-all clean-contracts

bootstrap-contracts:
	./scripts/bootstrap_contracts.sh

prepare-openapi:
	.venv/bin/python scripts/prepare_openapi.py

validate-supply-chain:
	.venv/bin/python scripts/check_supply_chain.py

validate-static:
	.venv/bin/python scripts/offline_static_audit.py

validate-jcs:
	.venv/bin/python scripts/jcs/verify_python.py
	node scripts/jcs/verify_node.mjs
	test -z "$$(gofmt -l scripts/jcs/go/*.go)"
	cd scripts/jcs/go && go test ./...

validate-compatibility:
	.venv/bin/python scripts/check_contract_compatibility.py

validate-contracts: prepare-openapi
	.venv/bin/python scripts/validate_contracts.py
	.venv/bin/python scripts/validate_semantics.py
	node scripts/lint_openapi_zero.mjs

bundle-openapi: prepare-openapi
	mkdir -p build
	npm run bundle:openapi

validate-all:
	./scripts/validate_all.sh
	$(MAKE) bundle-openapi

clean-contracts:
	rm -rf .venv node_modules build
