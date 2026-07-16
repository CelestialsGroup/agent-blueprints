.PHONY: bootstrap-contracts validate-contracts validate-jcs validate-supply-chain \
        bundle-openapi validate-all clean-contracts

bootstrap-contracts:
	./scripts/bootstrap_contracts.sh

validate-supply-chain:
	.venv/bin/python scripts/check_supply_chain.py

validate-static:
	.venv/bin/python scripts/offline_static_audit.py

validate-jcs:
	.venv/bin/python scripts/jcs/verify_python.py
	node scripts/jcs/verify_node.mjs
	cd scripts/jcs/go && go test ./...

validate-contracts:
	.venv/bin/python scripts/validate_contracts.py
	node_modules/.bin/redocly lint contracts/openapi/agent-access-v1.yaml
	node_modules/.bin/redocly lint contracts/openapi/plugin-invocation-v1.yaml
	node_modules/.bin/redocly lint contracts/openapi/delivery-webhook-v1.yaml
	node_modules/.bin/redocly lint contracts/openapi/sandbox-provider-v1.yaml

bundle-openapi:
	mkdir -p build
	npm run bundle:openapi

validate-all:
	./scripts/validate_all.sh
	$(MAKE) bundle-openapi

clean-contracts:
	rm -rf .venv node_modules build
