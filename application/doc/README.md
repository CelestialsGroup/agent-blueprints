# Implementation Documentation

This directory records implementation-specific decisions and operational
runbooks. It must not copy the Blueprint or Contract into a second authority.

- `decision/` explains local implementation choices within an accepted
  Blueprint boundary.
- `plan/` turns accepted Blueprint and Contract responsibilities into ordered,
  reviewable Application slices with explicit evidence and rollback boundaries.
- `runbook/` contains repeatable operating and recovery procedures.

Generated test evidence belongs under ignored `build/` paths and must bind the
exact Application, Blueprint, and Contract revisions and digests.
