"""Typer CLI for running EndpointKolauda audits."""

from __future__ import annotations

import glob
import json
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from kolauda.core.auditor import AuditReport, KolaudaAuditor, PathReport
from kolauda.core.engine import ResponseComparator

app = typer.Typer(help="EndpointKolauda JSON audit CLI.")
console = Console()


@app.callback()
def cli() -> None:
    """EndpointKolauda command group."""


class OutputFormat(str, Enum):
    """Output formats supported by the audit command."""

    table = "table"
    json = "json"
    markdown = "markdown"


@app.command("audit")
def audit(
    template: Path = typer.Option(..., "--template", help="Path to template JSON file."),
    samples: str = typer.Option(..., "--samples", help="Sample JSON path, directory, or glob."),
    output_format: OutputFormat = typer.Option(
        OutputFormat.table,
        "--format",
        help="Render output as table, json, or markdown.",
        case_sensitive=False,
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Print extra execution details."),
) -> None:
    """Compare sample responses against a template and print an audit report."""
    try:
        template_data = _load_json_file(template)
        sample_files = _resolve_sample_files(samples, template_path=template)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1)

    comparator = ResponseComparator()
    observations_by_response = []
    for sample_file in sample_files:
        try:
            sample_data = _load_json_file(sample_file)
        except ValueError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=1)

        observations_by_response.append(comparator.compare(template_data, sample_data))

    report = KolaudaAuditor(observations_by_response).generate_report()

    if output_format == OutputFormat.table:
        _render_table(report)
    elif output_format == OutputFormat.json:
        _render_json(report)
    else:
        _render_markdown(report)

    if verbose:
        console.print(
            "Processed "
            f"{len(sample_files)} sample files and "
            f"{len(report.by_path)} normalized fields."
        )


def _resolve_sample_files(samples: str, template_path: Path | None = None) -> list[Path]:
    sample_path = Path(samples)
    if sample_path.is_dir():
        matched = sorted(sample_path.glob("*.json"))
    else:
        matched = sorted(Path(path) for path in glob.glob(samples))

    files = [path for path in matched if path.is_file()]
    # Exclude the template file if present in the sample set
    if template_path is not None:
        files = [f for f in files if f.resolve() != template_path.resolve()]
    if not files:
        raise ValueError(f"No sample files found for pattern: {samples}")
    return files


def _load_json_file(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        raise ValueError(f"File not found: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error.msg}") from error


def _status_for_path(path_report: PathReport) -> tuple[str, str]:
    if path_report.type_drift:
        return "TYPE_DRIFT", "red"
    if path_report.is_always_null:
        return "ALWAYS_NULL", "yellow"
    if path_report.is_unstable and path_report.is_constant:
        return "OPTIONAL, CONSTANT", "yellow"
    if path_report.is_unstable:
        return "OPTIONAL", "yellow"
    if path_report.is_constant:
        return "CONSTANT", "yellow"
    return "OK", "green"


def _render_table(report: AuditReport) -> None:
    table = Table(title="Kolauda Audit")
    table.add_column("Field Path", style="cyan", no_wrap=True)
    table.add_column("Presence %", justify="right")
    table.add_column("Null %", justify="right")
    table.add_column("Unique Vals", justify="right")
    table.add_column("Status")

    for path, path_report in sorted(report.by_path.items()):
        status, color = _status_for_path(path_report)
        table.add_row(
            path,
            f"{path_report.presence_rate * 100:.1f}%",
            f"{path_report.null_rate * 100:.1f}%",
            str(len(path_report.field_audit.unique_values)),
            status,
            style=color,
        )

    console.print(table)


def _render_json(report: AuditReport) -> None:
    payload = {
        "total_responses": report.total_responses,
        "fields": [
            {
                "path": path_report.path,
                "presence_rate": path_report.presence_rate,
                "null_rate": path_report.null_rate,
                "unique_values": sorted(
                    str(value) for value in path_report.field_audit.unique_values
                ),
                "status": _status_for_path(path_report)[0],
                "flags": {
                    "is_always_null": path_report.is_always_null,
                    "is_constant": path_report.is_constant,
                    "type_drift": path_report.type_drift,
                    "is_unstable": path_report.is_unstable,
                },
            }
            for _, path_report in sorted(report.by_path.items())
        ],
    }
    console.print(json.dumps(payload, indent=2))


def _render_markdown(report: AuditReport) -> None:
    lines = [
        "| Field Path | Presence % | Null % | Unique Vals | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for path, path_report in sorted(report.by_path.items()):
        status, _ = _status_for_path(path_report)
        lines.append(
            "| "
            f"{path} | "
            f"{path_report.presence_rate * 100:.1f}% | "
            f"{path_report.null_rate * 100:.1f}% | "
            f"{len(path_report.field_audit.unique_values)} | "
            f"{status} |"
        )
    console.print("\n".join(lines))


def main() -> None:
    """Run the EndpointKolauda CLI app."""
    app()


if __name__ == "__main__":
    main()

