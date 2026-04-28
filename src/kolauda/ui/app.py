"""Streamlit dashboard for EndpointKolauda audits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kolauda.cli.main import (
    _collect_issue_statuses_by_path,
    _load_json_file,
    _resolve_sample_files,
    _status_for_path,
)
from kolauda.core.auditor import AuditReport, KolaudaAuditor
from kolauda.core.engine import IssueStatus, Observation, ResponseComparator


@dataclass(frozen=True)
class DashboardMetrics:
    """High-level numbers shown in the dashboard header."""

    total_files: int
    total_errors: int
    healthy_fields_percent: float


@dataclass(frozen=True)
class FieldDetails:
    """Detailed stats for one field path shown in the diff panel."""

    path: str
    status: str
    presence_percent: float
    null_percent: float
    unique_values: int
    observed_types: str


def run_audit(template: Path, samples: str) -> tuple[AuditReport, list[Observation], list[Path]]:
    """Execute the standard audit flow and return report data for the UI."""
    template_data = _load_json_file(template)
    sample_files = _resolve_sample_files(samples, template_path=template)

    comparator = ResponseComparator()
    observations_by_response: list[list[Observation]] = []
    for sample_file in sample_files:
        sample_data = _load_json_file(sample_file)
        observations_by_response.append(
            comparator.compare(
                template_data,
                sample_data,
                source_filename=sample_file.name,
            )
        )

    report = KolaudaAuditor(observations_by_response).generate_report()
    all_observations = [obs for response in observations_by_response for obs in response]
    return report, all_observations, sample_files


def compute_dashboard_metrics(
    report: AuditReport,
    observations: list[Observation],
    issue_statuses_by_path: dict[str, set[IssueStatus]],
    total_files: int,
) -> DashboardMetrics:
    """Compute headline metrics displayed above the audit table."""
    tracked_statuses = {IssueStatus.MISSING, IssueStatus.EXTRA, IssueStatus.TYPE_MISMATCH}
    total_errors = sum(1 for observation in observations if observation.status in tracked_statuses)

    healthy_fields = 0
    for path, path_report in report.by_path.items():
        status, _ = _status_for_path(path_report, issue_statuses_by_path.get(path))
        if status == "OK":
            healthy_fields += 1

    healthy_fields_percent = (
        (healthy_fields / len(report.by_path) * 100.0)
        if report.by_path
        else 0.0
    )
    return DashboardMetrics(
        total_files=total_files,
        total_errors=total_errors,
        healthy_fields_percent=healthy_fields_percent,
    )


def build_audit_rows(
    report: AuditReport,
    issue_statuses_by_path: dict[str, set[IssueStatus]],
) -> list[dict[str, Any]]:
    """Build row objects for st.dataframe from the audit report."""
    rows: list[dict[str, Any]] = []
    for path, path_report in sorted(report.by_path.items()):
        status, _ = _status_for_path(path_report, issue_statuses_by_path.get(path))
        rows.append(
            {
                "Field Path": path,
                "Presence %": round(path_report.presence_rate * 100.0, 1),
                "Null %": round(path_report.null_rate * 100.0, 1),
                "Unique Vals": len(path_report.field_audit.unique_values),
                "Status": status,
            }
        )
    return rows


def load_sample_json(path: Path) -> Any:
    """Load one sample JSON document for the explorer panel."""
    return _load_json_file(path)


def build_sample_file_map(sample_files: list[Path]) -> dict[str, Path]:
    """Map sample file names to paths for dropdown-based selection."""
    return {sample_file.name: sample_file for sample_file in sample_files}


def resolve_json_source(
    choice: str,
    template_payload: Any,
    sample_file_map: dict[str, Path],
) -> tuple[str, Any]:
    """Resolve a dropdown choice into a display label and JSON payload."""
    if choice == "Template":
        return "Template", template_payload
    if choice not in sample_file_map:
        raise ValueError(f"Unknown sample selection: {choice}")
    return choice, load_sample_json(sample_file_map[choice])


def build_diff_rows(left_payload: Any, right_payload: Any, right_label: str) -> list[dict[str, str]]:
    """Build a path-level diff table highlighting EXTRA and MISSING observations."""
    comparator = ResponseComparator()
    observations = comparator.compare(left_payload, right_payload, source_filename=right_label)

    grouped: dict[tuple[str, str, str], int] = {}
    for observation in observations:
        if observation.status not in {IssueStatus.MISSING, IssueStatus.EXTRA}:
            continue
        context = "<missing>" if observation.status == IssueStatus.MISSING else repr(observation.value)
        key = (observation.status.value, observation.path, context)
        grouped[key] = grouped.get(key, 0) + 1

    rows: list[dict[str, str]] = []
    for (issue_type, field_path, context), count in sorted(grouped.items(), key=lambda item: item[0][1]):
        context_value = context if count == 1 else f"{context} (x{count})"
        rows.append(
            {
                "Issue Type": issue_type,
                "Field Path": field_path,
                "Context": context_value,
            }
        )
    return rows


def build_field_details(
    path: str,
    report: AuditReport,
    issue_statuses_by_path: dict[str, set[IssueStatus]],
) -> FieldDetails | None:
    """Build detailed field statistics for the selected path."""
    path_report = report.by_path.get(path)
    if path_report is None:
        return None

    status, _ = _status_for_path(path_report, issue_statuses_by_path.get(path))
    observed_types = ", ".join(sorted(path_report.field_audit.observed_types)) or "-"
    return FieldDetails(
        path=path,
        status=status,
        presence_percent=path_report.presence_rate * 100.0,
        null_percent=path_report.null_rate * 100.0,
        unique_values=len(path_report.field_audit.unique_values),
        observed_types=observed_types,
    )


def main() -> None:
    """Run the Streamlit dashboard app."""
    import streamlit as st

    st.set_page_config(page_title="EndpointKolauda", page_icon="K", layout="wide")
    st.title("EndpointKolauda Dashboard")

    with st.sidebar:
        st.header("Inputs")
        template_path_input = st.text_input("Template File Path", value="examples/template.json")
        samples_path_input = st.text_input("Samples Directory Path", value="examples/samples")
        run_clicked = st.button("Run Kolauda", type="primary", use_container_width=True)

    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    if run_clicked:
        try:
            template_path = Path(template_path_input)
            template_payload = _load_json_file(template_path)
            report, observations, sample_files = run_audit(
                template=template_path,
                samples=samples_path_input,
            )
            issue_statuses_by_path = _collect_issue_statuses_by_path(observations)
            metrics = compute_dashboard_metrics(
                report=report,
                observations=observations,
                issue_statuses_by_path=issue_statuses_by_path,
                total_files=len(sample_files),
            )
            st.session_state.last_result = {
                "report": report,
                "observations": observations,
                "issue_statuses_by_path": issue_statuses_by_path,
                "sample_files": sample_files,
                "template_payload": template_payload,
                "metrics": metrics,
            }
        except ValueError as error:
            st.error(str(error))

    if st.session_state.last_result is None:
        st.info("Pick input paths in the sidebar and click 'Run Kolauda'.")
        return

    result = st.session_state.last_result
    report: AuditReport = result["report"]
    issue_statuses_by_path: dict[str, set[IssueStatus]] = result["issue_statuses_by_path"]
    sample_files: list[Path] = result["sample_files"]
    template_payload: Any = result["template_payload"]
    metrics: DashboardMetrics = result["metrics"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Files", metrics.total_files)
    col2.metric("Total Errors", metrics.total_errors)
    col3.metric("Healthy Fields %", f"{metrics.healthy_fields_percent:.1f}%")

    st.subheader("Audit Table")
    st.dataframe(build_audit_rows(report, issue_statuses_by_path), use_container_width=True)

    st.subheader("JSON Explorer")
    selected_sample = st.selectbox("Select sample file", options=sample_files, format_func=lambda p: p.name)
    try:
        sample_payload = load_sample_json(selected_sample)
        st.code(json.dumps(sample_payload, indent=2), language="json")
    except ValueError as error:
        st.error(str(error))

    st.subheader("Side-by-Side JSON Diff Viewer")
    sample_file_map = build_sample_file_map(sample_files)
    sample_names = sorted(sample_file_map.keys())

    if not sample_names:
        st.info("No sample files available for diff view.")
        return

    diff_selector_left, diff_selector_right = st.columns(2)
    left_choice = diff_selector_left.selectbox(
        "Left source",
        options=["Template", *sample_names],
        index=0,
        help="Baseline JSON. Defaults to template, but you can select a sample file.",
    )
    right_choice = diff_selector_right.selectbox(
        "Right source",
        options=sample_names,
        index=0,
        help="Comparison JSON file.",
    )

    try:
        left_label, left_payload = resolve_json_source(left_choice, template_payload, sample_file_map)
        right_label, right_payload = resolve_json_source(right_choice, template_payload, sample_file_map)
    except ValueError as error:
        st.error(str(error))
        return

    left_col, right_col = st.columns(2)
    left_col.markdown(f"**Left: {left_label}**")
    left_col.code(json.dumps(left_payload, indent=2), language="json")
    right_col.markdown(f"**Right: {right_label}**")
    right_col.code(json.dumps(right_payload, indent=2), language="json")

    diff_rows = build_diff_rows(left_payload, right_payload, right_label)
    st.markdown("**Highlighted EXTRA/MISSING Paths**")
    if diff_rows:
        st.dataframe(diff_rows, use_container_width=True)
    else:
        st.success("No EXTRA/MISSING differences found for this comparison.")

    st.markdown("**Field Details**")
    field_options = sorted({*report.by_path.keys(), *(row["Field Path"] for row in diff_rows)})
    if not field_options:
        st.info("No field paths available.")
        return

    selected_field = st.selectbox(
        "Select a field to inspect",
        options=field_options,
        help="Choose a path from the audit model to inspect cross-file statistics.",
    )
    details = build_field_details(selected_field, report, issue_statuses_by_path)
    if details is None:
        st.info("This path exists in the pair diff but has no aggregate stats in the current audit report.")
        return

    details_col1, details_col2, details_col3, details_col4 = st.columns(4)
    details_col1.metric("Status", details.status)
    details_col2.metric("Presence %", f"{details.presence_percent:.1f}%")
    details_col3.metric("Null %", f"{details.null_percent:.1f}%")
    details_col4.metric("Unique Values", details.unique_values)
    st.caption(f"Observed types: {details.observed_types}")


if __name__ == "__main__":
    main()

