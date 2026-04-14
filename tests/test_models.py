from kolauda.core.models import FieldAudit


def test_is_static_true_for_single_non_null_value() -> None:
    audit = FieldAudit(
        path="user.address.city",
        occurrence_count=3,
        null_count=0,
        unique_values={"Berlin"},
        observed_types={"str"},
    )

    assert audit.is_static is True


def test_is_static_false_when_nulls_exist() -> None:
    audit = FieldAudit(
        path="user.address.city",
        occurrence_count=3,
        null_count=1,
        unique_values={"Berlin"},
        observed_types={"str", "NoneType"},
    )

    assert audit.is_static is False


def test_is_static_false_for_multiple_values() -> None:
    audit = FieldAudit(
        path="user.address.city",
        occurrence_count=3,
        null_count=0,
        unique_values={"Berlin", "Paris"},
        observed_types={"str"},
    )

    assert audit.is_static is False


def test_null_count_cannot_exceed_occurrence_count() -> None:
    try:
        FieldAudit(path="user.address.city", occurrence_count=1, null_count=2)
        assert False, "Expected FieldAudit validation to fail"
    except ValueError as exc:
        assert "null_count" in str(exc)

