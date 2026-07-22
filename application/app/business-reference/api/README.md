# Business Reference API

Phase: **0C, not implemented**.

This directory will contain an independent Go module for Product, Entitlement,
Quota Reservation, Commercial Authorization, WorkSession exchange, revocation,
and Settlement receipt endpoints. It owns a separate process, dependency lock,
database connection, and signing identity.

It may call Agent Access only through public contracts. It must not import the
Agent Platform Go kernel or read the Agent Platform database.
