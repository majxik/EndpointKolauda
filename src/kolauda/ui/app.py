"""Streamlit dashboard for EndpointKolauda audits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from kolauda.cli.main import (
    _collect_issue_statuses_by_path,
    _load_json_file,
    _resolve_sample_files,
    _status_for_path,
)
from kolauda.core.auditor import AuditReport, KolaudaAuditor
from kolauda.core.engine import IssueStatus, Observation, ResponseComparator
from kolauda.core.history import (
    load_history_entries,
    load_history_entry,
    save_history_entry,
    validate_history_entry,
)


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


def minimal_plus_tab_labels() -> tuple[str, str, str, str]:
    """Return the fixed Minimal+ tab order used by the dashboard."""
    return ("Overview", "Diff", "Raw JSON", "History")


def resolve_base_directory(base_path: str) -> Path:
    """Resolve a user-provided base path to an existing directory."""
    candidate = Path(base_path).expanduser()
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    return Path.cwd().resolve()


def list_picker_entries(directory: Path) -> tuple[list[Path], list[Path]]:
    """Return sorted subdirectories and JSON files for picker navigation."""
    try:
        entries = list(directory.iterdir())
    except (FileNotFoundError, PermissionError, OSError):
        return [], []

    directories = sorted((entry for entry in entries if entry.is_dir()), key=lambda path: path.name.lower())
    json_files = sorted(
        (entry for entry in entries if entry.is_file() and entry.suffix.lower() == ".json"),
        key=lambda path: path.name.lower(),
    )
    return directories, json_files


def to_display_path(path: Path) -> str:
    """Render filesystem paths for UI controls in a consistent way."""
    return str(path.resolve())


def default_history_directory() -> Path:
    """Return the default local history directory used by the Streamlit UI."""
    return Path.cwd() / ".kolauda" / "history"


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


def build_overview_issue_rows(audit_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build compact EXTRA/MISSING summary rows for the Overview tab."""
    summary_rows: list[dict[str, Any]] = []
    for row in audit_rows:
        status = str(row.get("Status", ""))
        issue_types: list[str] = []
        if "EXTRA" in status:
            issue_types.append("EXTRA")
        if "MISSING" in status:
            issue_types.append("MISSING")
        if not issue_types:
            continue

        for issue_type in issue_types:
            summary_rows.append(
                {
                    "Issue Type": issue_type,
                    "Field Path": str(row.get("Field Path", "")),
                    "Status": status,
                }
            )

    return summary_rows


def load_sample_json(path: Path) -> Any:
    """Load one sample JSON document for the explorer panel."""
    return _load_json_file(path)


def build_sample_file_map(sample_files: list[Path]) -> dict[str, Path]:
    """Map sample file names to paths for dropdown-based selection."""
    return {sample_file.name: sample_file for sample_file in sample_files}


def build_sample_payload_map(sample_files: list[Path]) -> dict[str, Any]:
    """Map sample file names to preloaded JSON payloads for selectors and history."""
    return {sample_file.name: load_sample_json(sample_file) for sample_file in sample_files}


def resolve_json_source(
    choice: str,
    template_payload: Any,
    sample_source_map: dict[str, Any],
) -> tuple[str, Any]:
    """Resolve a dropdown choice into a display label and JSON payload."""
    if choice == "Template":
        return "Template", template_payload
    if choice not in sample_source_map:
        raise ValueError(f"Unknown sample selection: {choice}")

    value = sample_source_map[choice]
    if isinstance(value, Path):
        return choice, load_sample_json(value)
    return choice, value


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


def build_field_details_by_path(
    report: AuditReport,
    issue_statuses_by_path: dict[str, set[IssueStatus]],
) -> dict[str, dict[str, Any]]:
    """Create a serializable lookup for per-path field detail metrics."""
    details_by_path: dict[str, dict[str, Any]] = {}
    for path in report.by_path:
        details = build_field_details(path, report, issue_statuses_by_path)
        if details is None:
            continue
        details_by_path[path] = {
            "path": details.path,
            "status": details.status,
            "presence_percent": details.presence_percent,
            "null_percent": details.null_percent,
            "unique_values": details.unique_values,
            "observed_types": details.observed_types,
        }
    return details_by_path


def resolve_field_details(
    path: str,
    field_details_by_path: dict[str, dict[str, Any]],
) -> FieldDetails | None:
    """Resolve one path from serialized detail map to a FieldDetails model."""
    details = field_details_by_path.get(path)
    if details is None:
        return None

    return FieldDetails(
        path=str(details.get("path", path)),
        status=str(details.get("status", "OK")),
        presence_percent=float(details.get("presence_percent", 0.0)),
        null_percent=float(details.get("null_percent", 0.0)),
        unique_values=int(details.get("unique_values", 0)),
        observed_types=str(details.get("observed_types", "-")),
    )


def build_history_entry(
    *,
    template_path_input: str,
    samples_path_input: str,
    sample_files: list[Path],
    metrics: DashboardMetrics,
    audit_rows: list[dict[str, Any]],
    field_details_by_path: dict[str, dict[str, Any]],
    template_payload: Any,
    sample_payload_map: dict[str, Any],
) -> dict[str, Any]:
    """Create one persistable history snapshot from the current UI run."""
    timestamp_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    endpoint_key = Path(samples_path_input).name or "unknown"
    return {
        # Keep payload backward-compatible for older running app processes.
        # Updated validators normalize and persist this as schema v2.
        "schema_version": 1,
        "audit_id": uuid4().hex,
        "timestamp_utc": timestamp_utc,
        "inputs": {
            "template_path": template_path_input,
            "samples_path": samples_path_input,
            "sample_files": [sample_file.name for sample_file in sample_files],
        },
        "metadata": {
            "endpoint_key": endpoint_key,
            "endpoint_label": "",
            "environment": "",
            "notes": "",
        },
        "metrics": {
            "total_files": metrics.total_files,
            "total_errors": metrics.total_errors,
            "healthy_fields_percent": metrics.healthy_fields_percent,
        },
        "template_payload": template_payload,
        "sample_payloads": sample_payload_map,
        "audit_rows": audit_rows,
        "field_details_by_path": field_details_by_path,
    }


def history_chart_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build chart-ready rows for selectable history trend metrics."""
    return history_chart_rows_for_metric(entries, metric_key="total_errors")


def history_chart_rows_for_metric(entries: list[dict[str, Any]], metric_key: str) -> list[dict[str, Any]]:
    """Build chart-ready rows for one metric over time."""
    metric_to_label = {
        "total_errors": "Total Errors",
        "healthy_fields_percent": "Healthy Fields %",
    }
    if metric_key not in metric_to_label:
        raise ValueError(f"Unsupported history metric: {metric_key}")

    chart_label = metric_to_label[metric_key]
    rows: list[dict[str, Any]] = []
    for entry in entries:
        metrics = entry.get("metrics", {})
        metric_value = float(metrics.get(metric_key, 0.0))
        metadata = entry.get("metadata", {})
        rows.append(
            {
                "Timestamp": str(entry.get("timestamp_utc", "")),
                chart_label: metric_value,
                "Endpoint": str(metadata.get("endpoint_key", "unknown")),
            }
        )
    return rows


def _parse_iso_timestamp(value: str) -> datetime | None:
    """Parse stored timestamp values and return timezone-aware UTC datetimes."""
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def filter_history_entries(
    entries: list[dict[str, Any]],
    *,
    endpoint_key: str,
    start_timestamp_utc: str,
    end_timestamp_utc: str,
) -> list[dict[str, Any]]:
    """Filter history entries by endpoint and optional UTC timestamp bounds."""
    selected_endpoint = endpoint_key.strip()
    start_dt = _parse_iso_timestamp(start_timestamp_utc)
    end_dt = _parse_iso_timestamp(end_timestamp_utc)

    filtered: list[dict[str, Any]] = []
    for entry in entries:
        metadata = entry.get("metadata", {})
        entry_endpoint = str(metadata.get("endpoint_key", "unknown"))
        if selected_endpoint != "All" and entry_endpoint != selected_endpoint:
            continue

        timestamp_dt = _parse_iso_timestamp(str(entry.get("timestamp_utc", "")))
        if start_dt is not None and (timestamp_dt is None or timestamp_dt < start_dt):
            continue
        if end_dt is not None and (timestamp_dt is None or timestamp_dt > end_dt):
            continue

        filtered.append(entry)
    return filtered


def has_live_result(last_result: Any) -> bool:
    """Return whether the UI currently has a loaded live/current audit result."""
    return isinstance(last_result, dict)


def _render_field_metrics(details: FieldDetails, st: Any) -> None:
    """Render the standard four-card field details panel."""
    details_col1, details_col2, details_col3, details_col4 = st.columns(4)
    details_col1.metric("Status", details.status)
    details_col2.metric("Presence %", f"{details.presence_percent:.1f}%")
    details_col3.metric("Null %", f"{details.null_percent:.1f}%")
    details_col4.metric("Unique Values", details.unique_values)
    st.caption(f"Observed types: {details.observed_types}")


def _render_diff_section(
    *,
    st: Any,
    title: str,
    template_payload: Any,
    sample_payload_map: dict[str, Any],
    field_details_by_path: dict[str, dict[str, Any]],
    key_prefix: str,
) -> None:
    """Render a reusable diff + field-details section for current or historical data."""
    st.subheader(title)
    sample_names = sorted(sample_payload_map.keys())

    if not sample_names:
        st.info("No sample files available for diff view.")
        return

    left_selector, right_selector = st.columns(2)
    left_choice = left_selector.selectbox(
        "Left source",
        options=["Template", *sample_names],
        index=0,
        key=f"{key_prefix}_left",
    )
    right_choice = right_selector.selectbox(
        "Right source",
        options=sample_names,
        index=0,
        key=f"{key_prefix}_right",
    )

    left_label, left_payload = resolve_json_source(left_choice, template_payload, sample_payload_map)
    right_label, right_payload = resolve_json_source(right_choice, template_payload, sample_payload_map)

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
    field_options = sorted({*field_details_by_path.keys(), *(row["Field Path"] for row in diff_rows)})
    if not field_options:
        st.info("No field paths available.")
        return

    selected_field = st.selectbox(
        "Select a field to inspect",
        options=field_options,
        key=f"{key_prefix}_field",
    )
    details = resolve_field_details(selected_field, field_details_by_path)
    if details is None:
        st.info("This path exists in the pair diff but has no aggregate stats in this snapshot.")
        return
    _render_field_metrics(details, st)


def main() -> None:
    """Run the Streamlit dashboard app."""
    import streamlit as st

    st.set_page_config(page_title="EndpointKolauda", page_icon="K", layout="wide")
    st.title("EndpointKolauda Dashboard")

    if "template_path_input" not in st.session_state:
        st.session_state.template_path_input = "examples/template.json"
    if "samples_path_input" not in st.session_state:
        st.session_state.samples_path_input = "examples/samples"
    if "picker_base_path" not in st.session_state:
        st.session_state.picker_base_path = "."
    if "picker_current_dir" not in st.session_state:
        st.session_state.picker_current_dir = to_display_path(resolve_base_directory("."))
    if "pending_template_path" not in st.session_state:
        st.session_state.pending_template_path = None
    if "pending_samples_path" not in st.session_state:
        st.session_state.pending_samples_path = None
    if "history_external_entries" not in st.session_state:
        st.session_state.history_external_entries = []
    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    # Apply picker selections before rendering widget-bound path inputs.
    if st.session_state.pending_template_path is not None:
        st.session_state.template_path_input = st.session_state.pending_template_path
        st.session_state.pending_template_path = None
    if st.session_state.pending_samples_path is not None:
        st.session_state.samples_path_input = st.session_state.pending_samples_path
        st.session_state.pending_samples_path = None

    with st.sidebar:
        st.header("Inputs")
        st.text_input("Template File Path", key="template_path_input")
        st.text_input("Samples Directory Path", key="samples_path_input")

        with st.expander("Path Picker", expanded=False):
            st.caption("Browse and select paths instead of typing them manually.")
            st.text_input("Picker Base Path", key="picker_base_path")

            if st.button("Go To Base", key="picker_go_to_base"):
                base_dir = resolve_base_directory(st.session_state.picker_base_path)
                st.session_state.picker_current_dir = to_display_path(base_dir)

            current_dir = resolve_base_directory(st.session_state.picker_current_dir)
            st.session_state.picker_current_dir = to_display_path(current_dir)
            st.caption(f"Current Folder: {st.session_state.picker_current_dir}")

            nav_col1, nav_col2 = st.columns(2)
            if nav_col1.button("Up", key="picker_up"):
                st.session_state.picker_current_dir = to_display_path(current_dir.parent)
                current_dir = resolve_base_directory(st.session_state.picker_current_dir)
            if nav_col2.button("Refresh", key="picker_refresh"):
                current_dir = resolve_base_directory(st.session_state.picker_current_dir)

            directories, json_files = list_picker_entries(current_dir)

            if directories:
                selected_directory_name = st.selectbox(
                    "Subfolders",
                    options=[directory.name for directory in directories],
                    key="picker_selected_subfolder",
                )
                if st.button("Open Folder", key="picker_open_folder"):
                    selected_directory = next(
                        directory
                        for directory in directories
                        if directory.name == selected_directory_name
                    )
                    st.session_state.picker_current_dir = to_display_path(selected_directory)
                    current_dir = selected_directory
            else:
                st.caption("No subfolders in current directory.")

            if json_files:
                selected_template_name = st.selectbox(
                    "Template JSON",
                    options=[file.name for file in json_files],
                    key="picker_selected_template",
                )
                if st.button("Use As Template", key="picker_use_template"):
                    selected_template = next(
                        json_file
                        for json_file in json_files
                        if json_file.name == selected_template_name
                    )
                    st.session_state.pending_template_path = to_display_path(selected_template)
                    st.rerun()
            else:
                st.caption("No JSON files in current directory.")

            sample_dir_choices = [current_dir, *directories]
            selected_samples_name = st.selectbox(
                "Samples Directory",
                options=[directory.name for directory in sample_dir_choices],
                key="picker_selected_samples_directory",
            )
            if st.button("Use As Samples", key="picker_use_samples"):
                selected_samples_dir = next(
                    directory
                    for directory in sample_dir_choices
                    if directory.name == selected_samples_name
                )
                st.session_state.pending_samples_path = to_display_path(selected_samples_dir)
                st.rerun()

        template_path_input = st.session_state.template_path_input
        samples_path_input = st.session_state.samples_path_input
        run_clicked = st.button("Run Kolauda", type="primary", use_container_width=True)

    if run_clicked:
        try:
            template_path = Path(template_path_input)
            template_payload = _load_json_file(template_path)
            report, observations, sample_files = run_audit(
                template=template_path,
                samples=samples_path_input,
            )
            sample_payload_map = build_sample_payload_map(sample_files)
            issue_statuses_by_path = _collect_issue_statuses_by_path(observations)
            metrics = compute_dashboard_metrics(
                report=report,
                observations=observations,
                issue_statuses_by_path=issue_statuses_by_path,
                total_files=len(sample_files),
            )
            audit_rows = build_audit_rows(report, issue_statuses_by_path)
            field_details_by_path = build_field_details_by_path(report, issue_statuses_by_path)

            st.session_state.last_result = {
                "template_payload": template_payload,
                "sample_payload_map": sample_payload_map,
                "metrics": metrics,
                "audit_rows": audit_rows,
                "field_details_by_path": field_details_by_path,
                "inputs": {
                    "template_path": template_path_input,
                    "samples_path": samples_path_input,
                },
            }

            history_entry = build_history_entry(
                template_path_input=template_path_input,
                samples_path_input=samples_path_input,
                sample_files=sample_files,
                metrics=metrics,
                audit_rows=audit_rows,
                field_details_by_path=field_details_by_path,
                template_payload=template_payload,
                sample_payload_map=sample_payload_map,
            )
            saved_to = save_history_entry(history_entry, default_history_directory())
            st.caption(f"Saved audit snapshot: {saved_to.name}")
        except ValueError as error:
            st.error(str(error))

    overview_tab, diff_tab, raw_json_tab, history_tab = st.tabs(list(minimal_plus_tab_labels()))

    live_result_available = has_live_result(st.session_state.last_result)
    if live_result_available:
        result = st.session_state.last_result
        template_payload: Any = result["template_payload"]
        sample_payload_map: dict[str, Any] = result["sample_payload_map"]
        metrics: DashboardMetrics = result["metrics"]
        audit_rows: list[dict[str, Any]] = result["audit_rows"]
        field_details_by_path: dict[str, dict[str, Any]] = result["field_details_by_path"]

    with overview_tab:
        if not live_result_available:
            st.info("No current audit loaded. Run Kolauda or load one from the History tab.")
        else:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Files", metrics.total_files)
            col2.metric("Total Errors", metrics.total_errors)
            col3.metric("Healthy Fields %", f"{metrics.healthy_fields_percent:.1f}%")

            st.markdown("**Highlighted EXTRA/MISSING Paths (Summary)**")
            overview_issue_rows = build_overview_issue_rows(audit_rows)
            if overview_issue_rows:
                st.dataframe(overview_issue_rows, use_container_width=True)
            else:
                st.success("No EXTRA/MISSING paths found in this audit.")

            st.subheader("Audit Table")
            st.dataframe(audit_rows, use_container_width=True)

    with diff_tab:
        if not live_result_available:
            st.info("No current audit loaded. Run Kolauda or load one from the History tab.")
        else:
            _render_diff_section(
                st=st,
                title="Side-by-Side JSON Diff Viewer",
                template_payload=template_payload,
                sample_payload_map=sample_payload_map,
                field_details_by_path=field_details_by_path,
                key_prefix="live_diff",
            )

    with raw_json_tab:
        if not live_result_available:
            st.info("No current audit loaded. Run Kolauda or load one from the History tab.")
        else:
            st.subheader("JSON Explorer")
            sample_names = sorted(sample_payload_map.keys())
            if not sample_names:
                st.info("No sample payloads available.")
            else:
                selected_sample_name = st.selectbox(
                    "Select sample file",
                    options=sample_names,
                )
                st.code(json.dumps(sample_payload_map[selected_sample_name], indent=2), language="json")

    with history_tab:
        st.subheader("History")
        history_dir = default_history_directory()
        st.caption(f"History directory: {to_display_path(history_dir)}")

        load_col1, load_col2 = st.columns([3, 1])
        history_path = load_col1.text_input(
            "Load previous audit JSON file",
            key="history_load_path",
            placeholder="C:/path/to/saved-audit.json",
        )
        # Keep button baseline aligned with the text input control (not its label).
        load_col2.markdown("<div style='height: 1.65rem;'></div>", unsafe_allow_html=True)
        if load_col2.button("Load File", use_container_width=True):
            try:
                loaded_entry = load_history_entry(Path(history_path))
                existing_ids = {
                    str(entry.get("audit_id", ""))
                    for entry in st.session_state.history_external_entries
                }
                if str(loaded_entry.get("audit_id", "")) not in existing_ids:
                    st.session_state.history_external_entries.append(loaded_entry)
                st.success("History file loaded.")
            except ValueError as error:
                st.error(str(error))

        uploaded_history_file = st.file_uploader(
            "Or upload a saved audit JSON",
            type=["json"],
            key="history_file_uploader",
        )
        if uploaded_history_file is not None:
            try:
                uploaded_payload = json.loads(uploaded_history_file.getvalue().decode("utf-8"))
                loaded_entry = validate_history_entry(uploaded_payload)
                existing_ids = {
                    str(entry.get("audit_id", ""))
                    for entry in st.session_state.history_external_entries
                }
                if str(loaded_entry.get("audit_id", "")) not in existing_ids:
                    st.session_state.history_external_entries.append(loaded_entry)
                st.success("Uploaded history loaded.")
            except (ValueError, json.JSONDecodeError) as error:
                st.error(f"Invalid uploaded history file: {error}")

        disk_entries = load_history_entries(history_dir)
        entries_by_id: dict[str, dict[str, Any]] = {}
        for entry in [*disk_entries, *st.session_state.history_external_entries]:
            audit_id = str(entry.get("audit_id", ""))
            if audit_id:
                entries_by_id[audit_id] = entry

        all_entries = sorted(
            entries_by_id.values(),
            key=lambda entry: str(entry.get("timestamp_utc", "")),
        )
        if not all_entries:
            st.info("No history snapshots found yet. Run at least one audit to populate history.")
            return

        endpoint_options = ["All", *sorted({
            str(entry.get("metadata", {}).get("endpoint_key", "unknown"))
            for entry in all_entries
        })]
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        selected_endpoint = filter_col1.selectbox(
            "Endpoint",
            options=endpoint_options,
            key="history_filter_endpoint",
        )
        start_timestamp = filter_col2.text_input(
            "From (UTC ISO, optional)",
            key="history_filter_start",
            placeholder="2026-05-01T00:00:00+00:00",
        )
        end_timestamp = filter_col3.text_input(
            "To (UTC ISO, optional)",
            key="history_filter_end",
            placeholder="2026-05-31T23:59:59+00:00",
        )

        filtered_entries = filter_history_entries(
            all_entries,
            endpoint_key=selected_endpoint,
            start_timestamp_utc=start_timestamp,
            end_timestamp_utc=end_timestamp,
        )
        if not filtered_entries:
            st.info("No snapshots match the selected endpoint/date filters.")
            return

        metric_col1, metric_col2 = st.columns([2, 1])
        selected_metric = metric_col1.selectbox(
            "Trend Metric",
            options=["total_errors", "healthy_fields_percent"],
            format_func=lambda value: "Total Errors" if value == "total_errors" else "Healthy Fields %",
            key="history_trend_metric",
        )
        metric_label = "Total Errors" if selected_metric == "total_errors" else "Healthy Fields %"
        metric_col2.caption(f"Showing {len(filtered_entries)} snapshots")

        st.markdown(f"**{metric_label} over Time**")
        st.line_chart(
            history_chart_rows_for_metric(filtered_entries, selected_metric),
            x="Timestamp",
            y=metric_label,
            use_container_width=True,
        )

        audit_option_labels = {
            str(entry.get("audit_id", "")): (
                f"{entry.get('timestamp_utc', '')} | "
                f"endpoint={entry.get('metadata', {}).get('endpoint_key', 'unknown')} | "
                f"errors={entry.get('metrics', {}).get('total_errors', 0)}"
            )
            for entry in filtered_entries
        }

        selected_audit_id = st.selectbox(
            "Select audit snapshot",
            options=list(audit_option_labels.keys()),
            format_func=lambda audit_id: audit_option_labels[audit_id],
        )
        selected_entry = entries_by_id[selected_audit_id]
        selected_metadata = selected_entry.get("metadata", {})

        st.caption(
            " | ".join(
                [
                    f"Endpoint: {selected_metadata.get('endpoint_key', 'unknown')}",
                    f"Environment: {selected_metadata.get('environment', '-') or '-'}",
                    f"Label: {selected_metadata.get('endpoint_label', '-') or '-'}",
                ]
            )
        )
        if str(selected_metadata.get("notes", "")).strip():
            st.caption(f"Notes: {selected_metadata['notes']}")

        selected_metrics = selected_entry.get("metrics", {})
        hist_col1, hist_col2, hist_col3 = st.columns(3)
        hist_col1.metric("Total Files", int(selected_metrics.get("total_files", 0)))
        hist_col2.metric("Total Errors", int(selected_metrics.get("total_errors", 0)))
        hist_col3.metric(
            "Healthy Fields %",
            f"{float(selected_metrics.get('healthy_fields_percent', 0.0)):.1f}%",
        )

        st.markdown("**Audit Table Snapshot**")
        st.dataframe(selected_entry.get("audit_rows", []), use_container_width=True)

        if st.button("Load This Audit Into Main Tabs", use_container_width=True):
            selected_inputs = selected_entry.get("inputs", {})
            selected_samples = selected_entry.get("sample_payloads", {})
            st.session_state.last_result = {
                "template_payload": selected_entry.get("template_payload"),
                "sample_payload_map": selected_samples,
                "metrics": DashboardMetrics(
                    total_files=int(selected_metrics.get("total_files", 0)),
                    total_errors=int(selected_metrics.get("total_errors", 0)),
                    healthy_fields_percent=float(selected_metrics.get("healthy_fields_percent", 0.0)),
                ),
                "audit_rows": selected_entry.get("audit_rows", []),
                "field_details_by_path": selected_entry.get("field_details_by_path", {}),
                "inputs": {
                    "template_path": str(selected_inputs.get("template_path", "")),
                    "samples_path": str(selected_inputs.get("samples_path", "")),
                },
            }
            st.session_state.pending_template_path = str(selected_inputs.get("template_path", ""))
            st.session_state.pending_samples_path = str(selected_inputs.get("samples_path", ""))
            st.rerun()

        st.markdown("**Historical Diff & Field Details**")
        historical_template_payload = selected_entry.get("template_payload")
        historical_sample_payloads = selected_entry.get("sample_payloads", {})
        historical_field_details = selected_entry.get("field_details_by_path", {})
        _render_diff_section(
            st=st,
            title="Historical Snapshot Diff",
            template_payload=historical_template_payload,
            sample_payload_map=historical_sample_payloads,
            field_details_by_path=historical_field_details,
            key_prefix="history_diff",
        )


if __name__ == "__main__":
    main()

