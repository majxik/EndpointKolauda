# EndpointKolauda

EndpointKolauda is a Python toolkit for auditing JSON fields across multiple API responses.

## Requirements

- Python `>=3.10` (as defined in `pyproject.toml`)
- If your IDE shows Python 2.7 warnings (for example about `pathlib`), switch the project interpreter to the repository `.venv` or another Python 3.10+ interpreter.

## Setup

Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install project + dev dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Install Streamlit UI dependencies (optional):

```powershell
python -m pip install -e ".[ui]"
```

Verify interpreter and run tests:

```powershell
python -c "import sys; print(sys.version)"
python -m pytest
```

## Task runner shortcuts

Use the built-in PowerShell task script for common workflows:

```powershell
.\scripts\tasks.ps1 setup
.\scripts\tasks.ps1 test
.\scripts\tasks.ps1 audit-example
.\scripts\tasks.ps1 lint
```

If script execution is blocked, run once in your shell session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Optional: if you use `just`, equivalent commands are available via `justfile`:

```powershell
just setup
just test
just audit-example
just lint
```

## Project layout

- `src/kolauda/core/models.py`: Core Pydantic models.
- `src/kolauda/core/engine.py`: Recursive template/sample comparator.
- `src/kolauda/core/auditor.py`: Observation aggregator and statistical analyzer.
- `src/kolauda/cli/main.py`: Typer CLI for running audits.
- `src/kolauda/ui/app.py`: Streamlit dashboard for visual audit exploration.
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

You can provide `--samples` as:

- a glob pattern (for example `./data/*.json`)
- a directory path (all `*.json` files in that directory are loaded)
- a single JSON file path

Windows PowerShell examples:

```powershell
python -m kolauda.cli.main audit --template .\template.json --samples .\data
python -m kolauda.cli.main audit --template .\template.json --samples .\data --verbose
python -m kolauda.cli.main audit --template .\template.json --samples .\data\sample_01.json
```

If you prefer wildcard input in PowerShell, escape `*` so the shell does not expand it before Typer processes arguments:

```powershell
python -m kolauda.cli.main audit --template .\template.json --samples .\data\`*.json
```

Optional output formats:

```bash
python -m kolauda.cli.main audit --template ./template.json --samples "./data/*.json" --format json
python -m kolauda.cli.main audit --template ./template.json --samples "./data/*.json" --format markdown
```

## Run the Streamlit UI

Start the dashboard with:

```powershell
python -m streamlit run .\src\kolauda\ui\app.py
```

UI features in Ticket007 include:

- Sidebar inputs for template path and samples path
- `Run Kolauda` action that executes the same core audit engine as CLI
- Top metric cards (`Total Files`, `Total Errors`, `Healthy Fields %`)
- Audit table rendered with `st.dataframe`
- JSON explorer for viewing raw payloads of audited sample files

UI features in Ticket008 include:

- Side-by-side JSON selector (`Template` or sample on left, sample on right)
- Pairwise diff table that highlights `EXTRA` and `MISSING` field paths
- Field Details panel with aggregate stats (`Status`, `Presence %`, `Null %`, `Unique Values`, observed types)

UI features in Ticket010 include:

- Minimal+ tab layout: `Overview`, `Diff`, `Raw JSON`, `History`
- Shared sidebar controls across tabs (template path, samples path, run action)
- In-app sidebar path picker for browsing folders and selecting template/samples paths

UI features in Ticket009 include:

- Automatic snapshot persistence for each audit run into `.kolauda/history/*.json`
- `History` tab trend chart for `Error Count over Time`
- Historical snapshot selector with metrics + audit table preview
- Historical diff and field-details inspector (same style as live `Diff` tab)
- Load a saved audit JSON from disk (path input or file upload) and restore it into main tabs

UI features in Ticket011 (MVP) include:

- Endpoint-aware history metadata on new snapshots (`endpoint_key` inferred from samples path)
- Backward-compatible loading for older history snapshot schema
- History filters by endpoint and optional UTC date range
- Trend metric selector in History tab (`Total Errors` or `Healthy Fields %`)

## Report columns

- `Field Path`: normalized field path (list indexes are normalized as `[]`)
- `Presence %`: in how many responses the field appears
- `Null %`: among present observations, how often the value is `null`
- `Unique Vals`: number of distinct non-null values seen
- `Status`: derived warnings/health indicator for the field

## Status meanings

When multiple status labels apply to one field, they are always shown in this fixed order:

- `MISSING`, `EXTRA`, `TYPE_DRIFT`, `NULLABLE`, `ALWAYS_NULL`, `OPTIONAL?`, `CONSTANT`

- `TYPE_DRIFT`: multiple data types seen for the same field path
- `NULLABLE`: field is sometimes `null` and sometimes a consistent non-null type
- `ALWAYS_NULL`: field is present but always `null`
- `OPTIONAL?`: field is present in some responses but missing in others (`0% < Presence < 100%`)
- `MISSING`: field never appears in audited responses (`Presence = 0%`)
- `CONSTANT`: field appears in multiple responses and non-null value does not change
- `OK`: no warning conditions triggered

## Troubleshooting

- `File not found`: verify `--template` and `--samples` paths are correct.
- `No sample files found`: check glob syntax and file extension (`.json`).
- `Invalid JSON`: one of the files is malformed; validate with a JSON linter/editor.
- IDE warns about Python 2.7 modules: select a Python 3.10+ interpreter for this project.

## Minimal example

This repository includes ready-to-run example files:

- `examples/template.json`
- `examples/samples/response_01.json`
- `examples/samples/response_02.json`
- `examples/samples/response_03.json`

The example dataset is intentionally crafted to exercise all main status labels (`MISSING`, `EXTRA`, `TYPE_DRIFT`, `NULLABLE`, `ALWAYS_NULL`, `OPTIONAL?`, `CONSTANT`, `OK`).

Run this command:

```powershell
python -m kolauda.cli.main audit --template .\examples\template.json --samples .\examples\samples
```

You can also inspect machine-friendly output:

```powershell
python -m kolauda.cli.main audit --template .\examples\template.json --samples .\examples\samples --format json
```

