from kolauda.core.engine import ResponseComparator


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

