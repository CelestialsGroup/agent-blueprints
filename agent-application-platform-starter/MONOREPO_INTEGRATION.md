# Local monorepo integration

From this package directory inside the actual local Git checkout:

```bash
./scripts/install_github_workflow.sh
git -C "$(git rev-parse --show-toplevel)" rm --cached -- .DS_Store  # only when tracked
git -C "$(git rev-parse --show-toplevel)" add .github/workflows/contracts.yml .gitignore
git -C "$(git rev-parse --show-toplevel)" status --short
```

Review and commit the root changes. Configure `AGENT_PLATFORM_CONTRACT_ROOT` to the package-relative path, and configure protected compatibility variables described in `docs/38_CONTRACT_CI_AND_PROVENANCE.md`. Then run the official commands and public CI.

The package Gate deliberately compares the root Workflow and `.gitignore` against committed `HEAD`, and rejects root `.DS_Store` in both index and `HEAD`. Copied or staged-only files are not activated. `scripts/test_monorepo_integration.py` executes this fail/fail/pass regression in a temporary Git repository.
