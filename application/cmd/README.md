# Process Entrypoints

Each child directory builds one deployable Go process. Entrypoints should only
load configuration, assemble dependencies, expose lifecycle endpoints, and
manage graceful shutdown. Domain rules belong under `internal/`.

Do not share mutable global state between processes. A new process requires an
independent operational reason such as scaling, privilege, network, or failure
isolation; package boundaries alone are not a reason to split a service.
