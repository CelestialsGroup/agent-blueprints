# Native Runtime Package

Implement the private Native Runtime Core here: request admission at the Port
boundary, Agent Loop, bounded context, command handling, cursor events,
checkpoint/restart, and governed Gateway clients.

Modules in this package must not read PostgreSQL or Temporal persistence, store
platform authority, expose secrets, or leak private Agent/Thread/Checkpoint
objects into public Contract payloads.
