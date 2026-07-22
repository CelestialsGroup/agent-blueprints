# Repository Scripts

This directory contains deterministic repository automation for builds,
dependency admission, code generation, validation, and evidence assembly.
Scripts may consume locked Blueprint and Contract checkouts read-only.

Scripts are not product components or Contract authorities. Pin their toolchains,
keep generated output under ignored `build/` paths, and make destructive or
networked maintenance actions explicit rather than part of normal validation.

`verify_dependency_lock.py` is the only maintenance entrypoint for refreshing
and validating the Application-owned Blueprint/Contract dependency lock.

`verify_phase0_traceability.py` validates Application evidence claims against
every locked `phase0_implementation_required` Contract mapping and emits an
explicit implemented/unimplemented report. A complete report is not itself a
claim that Phase 0B is complete.
