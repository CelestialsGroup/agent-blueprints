# TypeScript Packages

This directory is reserved for genuinely shared pnpm workspace packages such as
generated Contract clients or a small Workbench UI system. Create a package
only after at least two real consumers or an independently generated artifact
requires it.

Packages must not contain server-side domain truth, database models, mutable
authorization state, or a copied Contract. Dependency versions are exact and
owned by the Application workspace.
