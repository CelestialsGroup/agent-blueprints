# Local monorepo integration

From this package directory inside the actual local Git checkout:

```bash
./scripts/install_github_workflow.sh
git -C "$(git rev-parse --show-toplevel)" rm --cached -- .DS_Store  # only when tracked
git -C "$(git rev-parse --show-toplevel)" add .github/workflows/contracts.yml .gitignore
git -C "$(git rev-parse --show-toplevel)" status --short
```

Review and commit the root changes. Configure `AGENT_PLATFORM_CONTRACT_ROOT` to the package-relative path, and configure protected compatibility variables described in `docs/38_CONTRACT_CI_AND_PROVENANCE.md`. Then run the official commands and public CI.

The package Gate deliberately fails when the root Workflow or `.gitignore` integration is absent or divergent, or when `.DS_Store` remains tracked. A copied but uncommitted Workflow is not considered activated.
