.PHONY: bootstrap-contracts validate-contracts bundle-openapi clean-contracts

bootstrap-contracts:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-contracts.txt
	npm ci

validate-contracts:
	.venv/bin/python scripts/validate_contracts.py
	node_modules/.bin/redocly lint contracts/openapi/agent-access-v1.yaml
	node_modules/.bin/redocly lint contracts/openapi/plugin-invocation-v1.yaml
	node_modules/.bin/redocly lint contracts/openapi/delivery-webhook-v1.yaml
	node_modules/.bin/redocly lint contracts/openapi/sandbox-provider-v1.yaml

bundle-openapi:
	mkdir -p build
	npm run bundle:openapi

clean-contracts:
	rm -rf .venv node_modules build
