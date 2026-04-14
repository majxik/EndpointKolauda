# EndpointKolauda

EndpointKolauda is a Python toolkit for auditing JSON fields across multiple API responses.

## Requirements

- Python `>=3.10` (as defined in `pyproject.toml`)
- If your IDE shows Python 2.7 warnings (for example about `pathlib`), switch the project interpreter to the repository `.venv` or another Python 3.10+ interpreter.

## Project layout

- `src/kolauda/core/models.py`: Core Pydantic models.
- `src/kolauda/core/engine.py`: Recursive template/sample comparator.
- `src/kolauda/core/auditor.py`: Observation aggregator and statistical analyzer.
- `src/kolauda/cli/main.py`: Typer CLI for running audits.
- `tests/`: Pytest suite for models, comparator, auditor, and CLI.

## Quick start

```bash
python -m pip install -e .[dev]
python -m pytest
```

## Run the CLI

```bash
python -m kolauda.cli.main audit --template ./template.json --samples "./data/*.json"
```

Optional output formats:

```bash
python -m kolauda.cli.main audit --template ./template.json --samples "./data/*.json" --format json
python -m kolauda.cli.main audit --template ./template.json --samples "./data/*.json" --format markdown
```

