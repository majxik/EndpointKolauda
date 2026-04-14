"""Recursive comparison engine for template/sample JSON traversal."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

Path = tuple[str | int, ...]


class IssueStatus(str, Enum):
	"""Per-observation status emitted by the comparator."""

	OK = "OK"
	MISSING = "MISSING"
	EXTRA = "EXTRA"
	TYPE_MISMATCH = "TYPE_MISMATCH"


@dataclass(frozen=True)
class Observation:
    """A flat record describing one field encountered during comparison."""

    path: str
    value: Any
    data_type: str
    exists: bool
    expected_type: str | None = None
    status: IssueStatus = IssueStatus.OK
    source_filename: str | None = None

    @property
    def normalized_path(self) -> str:
        """Compatibility alias for the normalized path string."""
        return self.path

    @property
    def type_mismatch(self) -> bool:
        """True when expected and observed runtime types do not match."""
        return self.status == IssueStatus.TYPE_MISMATCH


class ResponseComparator:
	"""Walks template and sample JSON objects recursively and emits observations."""

	LIST_PLACEHOLDER = "[]"

	def compare(
		self,
		template: Any,
		sample: Any,
		path: Path = (),
		source_filename: str | None = None,
	) -> list[Observation]:
		"""Compare one template node against one sample node recursively."""
		if sample is None and template is not None:
			return [
				self._make_observation(
					path=path,
					value=sample,
					exists=True,
					expected_type=type(template).__name__,
					status=IssueStatus.OK,
					source_filename=source_filename,
				)
			]

		if isinstance(template, dict):
			return self._compare_dict(template, sample, path, source_filename)
		if isinstance(template, list):
			return self._compare_list(template, sample, path, source_filename)

		expected_type = type(template).__name__
		actual_type = type(sample).__name__
		status = (
			IssueStatus.TYPE_MISMATCH if expected_type != actual_type else IssueStatus.OK
		)
		return [
			self._make_observation(
				path=path,
				value=sample,
				exists=True,
				expected_type=expected_type,
				status=status,
				source_filename=source_filename,
			)
		]

	def _compare_dict(
		self,
		template: dict[str, Any],
		sample: Any,
		path: Path,
		source_filename: str | None,
	) -> list[Observation]:
		if not isinstance(sample, dict):
			return [
				self._make_observation(
					path=path,
					value=sample,
					exists=True,
					expected_type="dict",
					status=IssueStatus.TYPE_MISMATCH,
					source_filename=source_filename,
				)
			]

		observations: list[Observation] = []
		for key, template_value in template.items():
			child_path = path + (key,)
			if key not in sample:
				observations.append(
					self._make_observation(
						path=child_path,
						value=None,
						exists=False,
						expected_type=type(template_value).__name__,
						status=IssueStatus.MISSING,
						source_filename=source_filename,
					)
				)
				continue

			observations.extend(
				self.compare(
					template_value,
					sample[key],
					child_path,
					source_filename=source_filename,
				)
			)

		for key in sample:
			if key in template:
				continue
			observations.extend(
				self._collect_extra_observations(
					sample[key],
					path + (key,),
					source_filename=source_filename,
				)
			)

		return observations

	def _compare_list(
		self,
		template: list[Any],
		sample: Any,
		path: Path,
		source_filename: str | None,
	) -> list[Observation]:
		if not isinstance(sample, list):
			return [
				self._make_observation(
					path=path,
					value=sample,
					exists=True,
					expected_type="list",
					status=IssueStatus.TYPE_MISMATCH,
					source_filename=source_filename,
				)
			]

		observations: list[Observation] = []
		if not template:
			for index, item in enumerate(sample):
				observations.extend(
					self._collect_extra_observations(
						item,
						path + (index,),
						source_filename=source_filename,
					)
				)
			return observations

		schema = template[0]
		for index, item in enumerate(sample):
			observations.extend(
				self.compare(
					schema,
					item,
					path + (index,),
					source_filename=source_filename,
				)
			)
		return observations

	def _collect_extra_observations(
		self,
		value: Any,
		path: Path,
		source_filename: str | None,
	) -> list[Observation]:
		"""Emit EXTRA observations recursively for values absent from template schema."""
		if isinstance(value, dict):
			observations: list[Observation] = []
			for key, nested in value.items():
				observations.extend(
					self._collect_extra_observations(
						nested,
						path + (key,),
						source_filename=source_filename,
					)
				)
			return observations

		if isinstance(value, list):
			observations: list[Observation] = []
			for index, nested in enumerate(value):
				observations.extend(
					self._collect_extra_observations(
						nested,
						path + (index,),
						source_filename=source_filename,
					)
				)
			if observations:
				return observations

		return [
			self._make_observation(
				path=path,
				value=value,
				exists=True,
				expected_type=None,
				status=IssueStatus.EXTRA,
				source_filename=source_filename,
			)
		]

	def _make_observation(
		self,
		path: Path,
		value: Any,
		exists: bool,
		expected_type: str | None = None,
		status: IssueStatus = IssueStatus.OK,
		source_filename: str | None = None,
	) -> Observation:
		return Observation(
			path=self._normalize_path(path),
			value=value,
			data_type=type(value).__name__ if exists else "missing",
			exists=exists,
			expected_type=expected_type,
			status=status,
			source_filename=source_filename,
		)

	def _normalize_path(self, path: Path) -> str:
		"""Convert tuple path to dotted format with list indices replaced by []."""
		parts = [self.LIST_PLACEHOLDER if isinstance(part, int) else str(part) for part in path]
		return ".".join(parts)

