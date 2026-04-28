from kolauda.core.auditor import KolaudaAuditor
from kolauda.core.engine import Observation


def test_generate_report_flags_constant_field_across_three_responses() -> None:
    observations_by_response = [
        [
            Observation(path="meta.version", value="v1", data_type="str", exists=True),
            Observation(path="user.name", value="Ada", data_type="str", exists=True),
        ],
        [
            Observation(path="meta.version", value="v1", data_type="str", exists=True),
            Observation(path="user.name", value="Grace", data_type="str", exists=True),
        ],
        [
            Observation(path="meta.version", value="v1", data_type="str", exists=True),
            Observation(path="user.name", value="Linus", data_type="str", exists=True),
        ],
    ]

    auditor = KolaudaAuditor(observations_by_response)
    report = auditor.generate_report()

    version_report = report.by_path["meta.version"]
    user_name_report = report.by_path["user.name"]

    assert report.total_responses == 3
    assert version_report.is_constant is True
    assert version_report.field_audit.unique_values == {"v1"}
    assert version_report.is_unstable is False

    assert user_name_report.is_constant is False
    assert user_name_report.field_audit.unique_values == {"Ada", "Grace", "Linus"}


def test_generate_report_flags_type_drift_when_types_change() -> None:
    observations_by_response = [
        [Observation(path="user.id", value=1, data_type="int", exists=True)],
        [Observation(path="user.id", value="1", data_type="str", exists=True)],
        [Observation(path="user.id", value=3, data_type="int", exists=True)],
    ]

    auditor = KolaudaAuditor(observations_by_response)
    report = auditor.generate_report()

    user_id_report = report.by_path["user.id"]

    assert user_id_report.type_drift is True
    assert user_id_report.field_audit.observed_types == {"int", "str"}
    assert user_id_report.is_unstable is False
    assert user_id_report.presence_rate == 1.0


def test_generate_report_flags_unstable_when_presence_is_below_full() -> None:
    observations_by_response = [
        [Observation(path="user.email", value="ada@example.com", data_type="str", exists=True)],
        [],
        [Observation(path="user.email", value="grace@example.com", data_type="str", exists=True)],
    ]

    auditor = KolaudaAuditor(observations_by_response)
    report = auditor.generate_report()

    user_email_report = report.by_path["user.email"]

    assert user_email_report.is_unstable is True
    assert user_email_report.presence_rate == 2 / 3
    assert user_email_report.type_drift is False
    assert user_email_report.field_audit.occurrence_count == 2


def test_generate_report_treats_null_and_single_type_as_nullable_not_drift() -> None:
    observations_by_response = [
        [Observation(path="offer.discount", value=10, data_type="int", exists=True)],
        [Observation(path="offer.discount", value=None, data_type="NoneType", exists=True)],
        [Observation(path="offer.discount", value=None, data_type="NoneType", exists=True)],
    ]

    auditor = KolaudaAuditor(observations_by_response)
    report = auditor.generate_report()

    discount_report = report.by_path["offer.discount"]

    assert discount_report.is_nullable is True
    assert discount_report.type_drift is False
    assert discount_report.is_always_null is False


def test_generate_report_marks_parent_path_nullable_for_null_vs_object() -> None:
    observations_by_response = [
        [Observation(path="product.productLine", value=None, data_type="NoneType", exists=True)],
        [
            Observation(
                path="product.productLine",
                value={"name": "Ibuprofen", "urlPath": ""},
                data_type="dict",
                exists=True,
            )
        ],
    ]

    auditor = KolaudaAuditor(observations_by_response)
    report = auditor.generate_report()

    product_line_report = report.by_path["product.productLine"]

    assert product_line_report.presence_rate == 1.0
    assert product_line_report.null_rate == 0.5
    assert product_line_report.is_nullable is True
    assert product_line_report.is_always_null is False
    assert product_line_report.is_unstable is False


