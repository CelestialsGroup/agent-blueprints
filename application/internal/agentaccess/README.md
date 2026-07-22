# Agent Access Adapter

This package currently provides the Agent Access process lifecycle and HTTP
router. It will remain a thin transport/composition adapter as Phase 0B routes
are added.

Request parsing, body limits, authentication context, and response mapping may
live here. Domain transitions, authorization consumption, and SQL transactions
must be delegated to explicit application services and repositories.
