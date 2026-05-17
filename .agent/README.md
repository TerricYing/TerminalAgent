# .agent layout

This folder is reserved for runtime config and runtime data.

- `models/`: provider and profile configuration.
- `security/`: users, roles, and tool permissions.
- `plans/`: executable plan definitions.
- `sessionlogs/`: session event logs.
- `memory/`: persisted memory files.
- `runtime/`: runtime-only state (db, workspaces, tmp).

Do not store build artifacts here.
