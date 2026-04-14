# EndpointKolauda

EndpointKolauda is a Python toolkit for auditing JSON fields across multiple API responses.

## Project layout

- `src/kolauda/core/models.py`: Core Pydantic models.
- `src/kolauda/core/engine.py`: Placeholder for recursive aggregation engine logic.
- `src/kolauda/cli/main.py`: CLI entrypoint placeholder.
- `tests/test_models.py`: Initial pytest coverage for `FieldAudit`.

## Quick start

```bash
python -m pip install -e .[dev]
python -m pytest
```

