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
from kolauda.core.engine import IssueStatus, Observation, ResponseComparator

app = typer.Typer(help="EndpointKolauda JSON audit CLI.")
console = Console()

STATUS_LABEL_ORDER = (
    "MISSING",
    "EXTRA",
    "TYPE_DRIFT",
    "NULLABLE",
    "ALWAYS_NULL",
    "OPTIONAL?",
    "CONSTANT",
)


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
    observations_by_response: list[list[Observation]] = []
    audited_filenames = [sample_file.name for sample_file in sample_files]
    for sample_file in sample_files:
        try:
            sample_data = _load_json_file(sample_file)
        except ValueError as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=1)

        observations_by_response.append(
            comparator.compare(
                template_data,
                sample_data,
                source_filename=sample_file.name,
            )
        )

    report = KolaudaAuditor(observations_by_response).generate_report()
    all_observations = [obs for response in observations_by_response for obs in response]
    issue_statuses_by_path = _collect_issue_statuses_by_path(all_observations)

    if output_format == OutputFormat.table:
        _render_summary(audited_filenames)
        _render_table(report, issue_statuses_by_path)
        _render_issue_log(all_observations)
    elif output_format == OutputFormat.json:
        _render_json(report, audited_filenames, issue_statuses_by_path)
    else:
        _render_markdown(report, audited_filenames, issue_statuses_by_path)

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


def _collect_issue_statuses_by_path(observations: list[Observation]) -> dict[str, set[IssueStatus]]:
    by_path: dict[str, set[IssueStatus]] = {}
    tracked = {IssueStatus.MISSING, IssueStatus.EXTRA, IssueStatus.TYPE_MISMATCH}
    for observation in observations:
        if observation.status not in tracked:
            continue
        by_path.setdefault(observation.path, set()).add(observation.status)
    return by_path


def _status_for_path(
    path_report: PathReport,
    issue_statuses: set[IssueStatus] | None = None,
) -> tuple[str, str]:
    issue_statuses = issue_statuses or set()
    has_missing_events = IssueStatus.MISSING in issue_statuses
    is_fully_missing = path_report.presence_rate == 0.0 and has_missing_events
    is_partially_present = 0.0 < path_report.presence_rate < 1.0

    active_labels = {
        "MISSING": is_fully_missing,
        "EXTRA": IssueStatus.EXTRA in issue_statuses,
        "TYPE_DRIFT": IssueStatus.TYPE_MISMATCH in issue_statuses or path_report.type_drift,
        "NULLABLE": path_report.is_nullable,
        "ALWAYS_NULL": path_report.is_always_null,
        "OPTIONAL?": is_partially_present,
        "CONSTANT": path_report.is_constant,
    }
    labels = [label for label in STATUS_LABEL_ORDER if active_labels[label]]

    if not labels:
        return "OK", "green"
    if "MISSING" in labels:
        return ", ".join(labels), "bold red"
    if "EXTRA" in labels:
        return ", ".join(labels), "bold magenta"
    if "TYPE_DRIFT" in labels:
        return ", ".join(labels), "red"
    return ", ".join(labels), "yellow"


def _render_summary(audited_filenames: list[str]) -> None:
    filenames = ", ".join(audited_filenames)
    console.print(
        f"Audited Files ({len(audited_filenames)}): [{filenames}]",
        style="bold",
        markup=False,
    )


def _render_table(
    report: AuditReport,
    issue_statuses_by_path: dict[str, set[IssueStatus]],
) -> None:
    table = Table(title="Kolauda Audit")
    table.add_column("Field Path", style="cyan", no_wrap=True)
    table.add_column("Presence %", justify="right")
    table.add_column("Null %", justify="right")
    table.add_column("Unique Vals", justify="right")
    table.add_column("Status")

    for path, path_report in sorted(report.by_path.items()):
        status, color = _status_for_path(path_report, issue_statuses_by_path.get(path))
        table.add_row(
            path,
            f"{path_report.presence_rate * 100:.1f}%",
            f"{path_report.null_rate * 100:.1f}%",
            str(len(path_report.field_audit.unique_values)),
            status,
            style=color,
        )

    console.print(table)


def _render_json(
    report: AuditReport,
    audited_filenames: list[str],
    issue_statuses_by_path: dict[str, set[IssueStatus]],
) -> None:
    payload = {
        "total_responses": report.total_responses,
        "audited_files": audited_filenames,
        "fields": [
            {
                "path": path_report.path,
                "presence_rate": path_report.presence_rate,
                "null_rate": path_report.null_rate,
                "unique_values": sorted(
                    str(value) for value in path_report.field_audit.unique_values
                ),
                "status": _status_for_path(
                    path_report,
                    issue_statuses_by_path.get(path_report.path),
                )[0],
                "flags": {
                    "is_nullable": path_report.is_nullable,
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


def _render_markdown(
    report: AuditReport,
    audited_filenames: list[str],
    issue_statuses_by_path: dict[str, set[IssueStatus]],
) -> None:
    lines = [
        f"Audited Files ({len(audited_filenames)}): [{', '.join(audited_filenames)}]",
        "",
        "| Field Path | Presence % | Null % | Unique Vals | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for path, path_report in sorted(report.by_path.items()):
        status, _ = _status_for_path(path_report, issue_statuses_by_path.get(path))
        lines.append(
            "| "
            f"{path} | "
            f"{path_report.presence_rate * 100:.1f}% | "
            f"{path_report.null_rate * 100:.1f}% | "
            f"{len(path_report.field_audit.unique_values)} | "
            f"{status} |"
        )
    console.print("\n".join(lines))


def _render_issue_log(observations: list[Observation]) -> None:
    """Print row-level issues after the statistical table."""
    issue_observations = [
        obs
        for obs in observations
        if obs.status in {IssueStatus.MISSING, IssueStatus.EXTRA, IssueStatus.TYPE_MISMATCH}
    ]

    issue_table = Table(title="\N{POLICE CARS REVOLVING LIGHT} Detailed Issue Log")
    issue_table.add_column("File", style="cyan")
    issue_table.add_column("Issue Type")
    issue_table.add_column("Field Path", style="white")
    issue_table.add_column("Context Value")

    grouped: dict[tuple[str, str, str, str], int] = {}
    for observation in issue_observations:
        context_value = (
            "<missing>"
            if observation.status == IssueStatus.MISSING
            else repr(observation.value)
        )

        key = (
            observation.source_filename or "<unknown>",
            observation.status.value,
            observation.path,
            context_value,
        )
        grouped[key] = grouped.get(key, 0) + 1

    for (filename, issue_type, field_path, context_value), count in sorted(
        grouped.items(),
        key=lambda item: (item[0][2], item[0][0], item[0][1]),
    ):
        status = IssueStatus(issue_type)
        style = "white"
        if status == IssueStatus.EXTRA:
            style = "bold magenta"
        elif status == IssueStatus.MISSING:
            style = "bold red"
        elif status == IssueStatus.TYPE_MISMATCH:
            style = "yellow"

        context_display = context_value if count == 1 else f"{context_value} (x{count})"

        issue_table.add_row(
            filename,
            issue_type,
            field_path,
            context_display,
            style=style,
        )

    if not issue_observations:
        console.print(
            "\N{POLICE CARS REVOLVING LIGHT} Detailed Issue Log: "
            "no row-level issues detected."
        )
        return

    console.print(issue_table)


def main() -> None:
    """Run the EndpointKolauda CLI app."""
    app()


if __name__ == "__main__":
    main()

