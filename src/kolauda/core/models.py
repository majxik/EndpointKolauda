"""Pydantic models used by the EndpointKolauda audit pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldAudit(BaseModel):
    """Stores aggregated statistics for one JSON path across many responses."""

    model_config = ConfigDict(frozen=False)

    path: str = Field(min_length=1, description="Dot-separated JSON path.")
    occurrence_count: int = Field(
        ge=0,
        description="How many samples contained this field (including null values).",
    )
    null_count: int = Field(
        default=0,
        ge=0,
        description="How many observed values for this field were null.",
    )
    unique_values: set[Any] = Field(
        default_factory=set,
        description="Unique hashable values observed for this field.",
    )
    observed_types: set[str] = Field(
        default_factory=set,
        description="Distinct Python data type names observed for this field.",
    )

    @model_validator(mode="after")
    def validate_counts(self) -> "FieldAudit":
        """Ensure counters remain internally consistent."""
        if self.null_count > self.occurrence_count:
            raise ValueError("null_count cannot be greater than occurrence_count")
        return self

    @property
    def is_static(self) -> bool:
        """True when every observed value is the same non-null value."""
        return (
            self.occurrence_count > 0
            and self.null_count == 0
            and len(self.unique_values) == 1
        )

