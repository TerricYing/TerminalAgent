# TerminalAgent

A pure terminal, multi-user agent runtime with process-level isolation, role-based tools, schedule support, and no UI.

## Core guarantees

- Each task session is isolated in its own subprocess and workspace.
- Development sources, runtime data, and build outputs are physically separated.
- `.agent` holds runtime configuration and runtime state.

## Directory boundaries

- `src/`, `tests/`: development code only.
- `.agent/`: runtime configuration and runtime state only.
- `dist/`, `build/`: packaging output only.

## Quick start

1. Create a Python 3.10+ environment.
2. Install in editable mode:
   - `pip install -e .`
3. Validate config:
   - `agent config validate`
4. Inspect schedule state:
   - `agent schedule list`

## Implemented CLI (initial)

- `agent config validate`
- `agent schedule add --id ... --user ... --role ... --run-at ... --command ...`
- `agent schedule list`
- `agent schedule remove --id ...`
- `agent schedule tick [--now ...]`
- `agent memory set|get|list|clear`
- `agent logs tail --user ... --session ...`
- `agent run --user ... --role ... --shell ...`
- `agent plan run --file ...`
