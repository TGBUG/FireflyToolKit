from pathlib import Path

import pytest

from fireflyer import drift

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def schema():
    return drift.parse_schema(FIXTURES / "content.config.ts")


def test_reads_every_collection(schema):
    assert set(schema) == {"posts", "spec"}


def test_empty_schema_collection_has_no_fields(schema):
    assert schema["spec"] == {}


def test_reads_plain_fields(schema):
    assert schema["posts"]["title"].kind == "string"
    assert schema["posts"]["title"].required is True


def test_defaults_and_optionals_are_not_required(schema):
    assert schema["posts"]["updated"].required is False
    assert schema["posts"]["tags"].required is False
    assert schema["posts"]["seriesOrder"].kind == "number"
    assert schema["posts"]["seriesOrder"].required is False


def test_method_name_on_the_next_line_is_read(schema):
    """Regression: `link: z\\n    .array(` used to be read as `object`."""
    assert schema["posts"]["link"].kind == "array"


def test_comments_do_not_derail_parsing(schema):
    # The `//` comment above `tags` contains a comma and a z.object({}).
    assert schema["posts"]["tags"].kind == "array"
    assert set(schema["posts"]) == {
        "title",
        "published",
        "author",
        "updated",
        "tags",
        "seriesOrder",
        "link",
    }


def test_matching_config_reports_no_errors(schema):
    config = drift.parse_config(FIXTURES / "config-ok.yml")
    assert [f for f in drift.compare(schema, config) if f.level == "error"] == []


def test_allowed_extras_are_ignored(schema):
    """`body`, `slug` and `_slug` live outside the schema on purpose."""
    config = drift.parse_config(FIXTURES / "config-ok.yml")
    errors = [f for f in drift.compare(schema, config) if f.level == "error"]
    assert errors == []


def test_reports_fields_the_schema_does_not_have(schema):
    config = drift.parse_config(FIXTURES / "config-bad.yml")
    errors = [f.message for f in drift.compare(schema, config) if f.level == "error"]
    assert any("posts.date" in message and "absent from the schema" in message for message in errors)


def test_reports_required_fields_missing_from_config(schema):
    config = drift.parse_config(FIXTURES / "config-bad.yml")
    errors = [f.message for f in drift.compare(schema, config) if f.level == "error"]
    assert any("posts.published" in message and "required by the schema" in message for message in errors)


def test_reports_required_fields_marked_optional(schema):
    config = drift.parse_config(FIXTURES / "config-bad.yml")
    errors = [f.message for f in drift.compare(schema, config) if f.level == "error"]
    assert any("posts.author" in message and "required:false" in message for message in errors)


def test_reports_a_collection_with_no_schema_counterpart(schema):
    config = drift.parse_config(FIXTURES / "config-bad.yml")
    errors = [f.message for f in drift.compare(schema, config) if f.level == "error"]
    assert any("settings" in message and "no matching collection" in message for message in errors)


def test_missing_schema_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        drift.parse_schema(tmp_path / "nope.ts")
