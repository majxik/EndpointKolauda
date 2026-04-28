from kolauda.core.engine import IssueStatus, ResponseComparator


def test_compare_nested_dicts_and_missing_keys() -> None:
    comparator = ResponseComparator()
    template = {"data": {"user": {"id": 1, "email": "x@example.com"}}}
    sample = {"data": {"user": {"id": 7}}}

    observations = comparator.compare(template, sample)

    id_obs = next(obs for obs in observations if obs.path == "data.user.id")
    missing_email_obs = next(obs for obs in observations if obs.path == "data.user.email")

    assert id_obs.exists is True
    assert id_obs.value == 7
    assert id_obs.type_mismatch is False

    assert missing_email_obs.exists is False
    assert missing_email_obs.data_type == "missing"
    assert missing_email_obs.status == IssueStatus.MISSING


def test_compare_detects_extra_keys_not_in_template() -> None:
    comparator = ResponseComparator()
    template = {"data": {"user": {"id": 1}}}
    sample = {"data": {"user": {"id": 7, "internal_id": "abc-123"}}}

    observations = comparator.compare(template, sample)
    extra_obs = next(obs for obs in observations if obs.path == "data.user.internal_id")

    assert extra_obs.status == IssueStatus.EXTRA
    assert extra_obs.exists is True
    assert extra_obs.value == "abc-123"


def test_compare_list_of_objects_uses_first_template_item_as_schema() -> None:
    comparator = ResponseComparator()
    template = {"users": [{"name": "", "age": 0}]}
    sample = {
        "users": [
            {"name": "Ada", "age": 37},
            {"name": "Grace", "age": 42},
        ]
    }

    observations = comparator.compare(template, sample)
    paths = [obs.path for obs in observations]

    assert "users.[].name" in paths
    assert "users.[].age" in paths
    assert all(".0." not in path and ".1." not in path for path in paths)
    assert paths.count("users.[].name") == 2
    assert paths.count("users.[].age") == 2


def test_compare_reports_type_mismatches() -> None:
    comparator = ResponseComparator()
    template = {"payload": {"count": 1, "items": [{"id": 1}]}}
    sample = {"payload": {"count": "one", "items": {"id": 10}}}

    observations = comparator.compare(template, sample)

    count_obs = next(obs for obs in observations if obs.path == "payload.count")
    items_obs = next(obs for obs in observations if obs.path == "payload.items")

    assert count_obs.exists is True
    assert count_obs.expected_type == "int"
    assert count_obs.data_type == "str"
    assert count_obs.type_mismatch is True

    assert items_obs.exists is True
    assert items_obs.expected_type == "list"
    assert items_obs.data_type == "dict"
    assert items_obs.type_mismatch is True


def test_compare_preserves_source_filename_for_all_observations() -> None:
    comparator = ResponseComparator()
    template = {"data": {"id": 1, "email": "x@example.com"}}
    sample = {"data": {"id": "one", "extra": True}}

    observations = comparator.compare(
        template,
        sample,
        source_filename="response_01.json",
    )

    assert observations
    assert all(obs.source_filename == "response_01.json" for obs in observations)


def test_compare_allows_null_without_type_mismatch() -> None:
    comparator = ResponseComparator()
    template = {"offer": {"discount": 10}}
    sample = {"offer": {"discount": None}}

    observations = comparator.compare(template, sample)
    discount_obs = next(obs for obs in observations if obs.path == "offer.discount")

    assert discount_obs.status == IssueStatus.OK
    assert discount_obs.type_mismatch is False


def test_compare_emits_parent_observation_for_dict_values() -> None:
    comparator = ResponseComparator()
    template = {"product": {"productLine": {"name": "", "urlPath": ""}}}
    sample = {"product": {"productLine": {"name": "Ibuprofen", "urlPath": ""}}}

    observations = comparator.compare(template, sample)
    product_line_obs = next(obs for obs in observations if obs.path == "product.productLine")

    assert product_line_obs.exists is True
    assert product_line_obs.data_type == "dict"
    assert product_line_obs.status == IssueStatus.OK


