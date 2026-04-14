"""Recursive comparison engine for template/sample JSON traversal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Path = tuple[str | int, ...]


@dataclass(frozen=True)
class Observation:
	"""A flat record describing one field encountered during comparison."""

	path: str
	value: Any
	data_type: str
	exists: bool
	expected_type: str | None = None

	@property
	def normalized_path(self) -> str:
		"""Compatibility alias for the normalized path string."""
		return self.path

	@property
	def type_mismatch(self) -> bool:
		"""True when expected and observed runtime types do not match."""
		return (
			self.exists
			and self.expected_type is not None
			and self.expected_type != self.data_type
		)


class ResponseComparator:
	"""Walks template and sample JSON objects recursively and emits observations."""

	LIST_PLACEHOLDER = "[]"

	def compare(self, template: Any, sample: Any, path: Path = ()) -> list[Observation]:
		"""Compare one template node against one sample node recursively."""
		if isinstance(template, dict):
			return self._compare_dict(template, sample, path)
		if isinstance(template, list):
			return self._compare_list(template, sample, path)

		return [
			self._make_observation(
				path=path,
				value=sample,
				exists=True,
				expected_type=type(template).__name__,
			)
		]

	def _compare_dict(self, template: dict[str, Any], sample: Any, path: Path) -> list[Observation]:
		if not isinstance(sample, dict):
			return [
				self._make_observation(
					path=path,
					value=sample,
					exists=True,
					expected_type="dict",
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
					)
				)
				continue

			observations.extend(self.compare(template_value, sample[key], child_path))
		return observations

	def _compare_list(self, template: list[Any], sample: Any, path: Path) -> list[Observation]:
		if not isinstance(sample, list):
			return [
				self._make_observation(
					path=path,
					value=sample,
					exists=True,
					expected_type="list",
				)
			]

		if not template:
			return []

		schema = template[0]
		observations: list[Observation] = []
		for index, item in enumerate(sample):
			observations.extend(self.compare(schema, item, path + (index,)))
		return observations

	def _make_observation(
		self,
		path: Path,
		value: Any,
		exists: bool,
		expected_type: str | None = None,
	) -> Observation:
		return Observation(
			path=self._normalize_path(path),
			value=value,
			data_type=type(value).__name__ if exists else "missing",
			exists=exists,
			expected_type=expected_type,
		)

	def _normalize_path(self, path: Path) -> str:
		"""Convert tuple path to dotted format with list indices replaced by []."""
		parts = [self.LIST_PLACEHOLDER if isinstance(part, int) else str(part) for part in path]
		return ".".join(parts)

