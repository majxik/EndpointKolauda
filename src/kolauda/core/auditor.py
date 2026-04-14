"""Audit aggregation and statistical analysis for EndpointKolauda."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from kolauda.core.engine import Observation
from kolauda.core.models import FieldAudit


@dataclass(frozen=True)
class PathReport:
    """Aggregated analysis for one normalized field path."""

    path: str
    field_audit: FieldAudit
    presence_rate: float
    null_rate: float
    is_always_null: bool
    is_constant: bool
    type_drift: bool
    is_unstable: bool


@dataclass(frozen=True)
class AuditReport:
    """Top-level report returned by the Kolauda auditor."""

    total_responses: int
    by_path: dict[str, PathReport]


class KolaudaAuditor:
    """Groups observations by path and computes consistency warnings."""

    def __init__(self, observations_by_response: list[list[Observation]]) -> None:
        self._observations_by_response = observations_by_response

    def generate_report(self) -> AuditReport:
        """Build path-level statistics and warning flags from raw observations."""
        grouped: dict[str, list[Observation]] = defaultdict(list)
        responses_with_presence: dict[str, set[int]] = defaultdict(set)

        for response_index, observations in enumerate(self._observations_by_response):
            seen_present_paths: set[str] = set()
            for observation in observations:
                path = observation.normalized_path
                grouped[path].append(observation)
                if observation.exists:
                    seen_present_paths.add(path)

            for path in seen_present_paths:
                responses_with_presence[path].add(response_index)

        total_responses = len(self._observations_by_response)
        by_path: dict[str, PathReport] = {}

        for path, observations in grouped.items():
            field_audit = self._build_field_audit(path, observations)
            presence_rate = (
                len(responses_with_presence[path]) / total_responses if total_responses else 0.0
            )
            null_rate = (
                field_audit.null_count / field_audit.occurrence_count
                if field_audit.occurrence_count
                else 0.0
            )

            is_always_null = (
                field_audit.occurrence_count > 0
                and field_audit.null_count == field_audit.occurrence_count
            )
            is_constant = (
                field_audit.occurrence_count > 1
                and field_audit.null_count < field_audit.occurrence_count
                and len(field_audit.unique_values) == 1
            )
            type_drift = len(field_audit.observed_types) > 1
            is_unstable = presence_rate < 1.0

            by_path[path] = PathReport(
                path=path,
                field_audit=field_audit,
                presence_rate=presence_rate,
                null_rate=null_rate,
                is_always_null=is_always_null,
                is_constant=is_constant,
                type_drift=type_drift,
                is_unstable=is_unstable,
            )

        return AuditReport(total_responses=total_responses, by_path=by_path)

    def _build_field_audit(self, path: str, observations: list[Observation]) -> FieldAudit:
        present_observations = [observation for observation in observations if observation.exists]
        occurrence_count = len(present_observations)
        null_count = sum(1 for observation in present_observations if observation.value is None)

        unique_values: set[Any] = set()
        for observation in present_observations:
            if observation.value is None:
                continue
            unique_values.add(self._to_hashable(observation.value))

        observed_types = {observation.data_type for observation in present_observations}

        return FieldAudit(
            path=path,
            occurrence_count=occurrence_count,
            null_count=null_count,
            unique_values=unique_values,
            observed_types=observed_types,
        )

    def _to_hashable(self, value: Any) -> Any:
        """Ensure values can be inserted into the FieldAudit unique-values set."""
        try:
            hash(value)
            return value
        except TypeError:
            return repr(value)

