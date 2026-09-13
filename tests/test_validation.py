from copy import deepcopy

import pytest

from csv_validator.validation import normalize_date, validate_rows, valid_amount, valid_email


def sample(**changes):
    return {"id": "001", "name": "テスト担当", "email": "test@example.com", "date": "2026-09-13", "amount": "1200.50", "category": "備品", **changes}


def test_valid_data_trims_all_values_without_mutating_input():
    rows = [{key: f"  {value}\u3000" for key, value in sample().items()}]
    original = deepcopy(rows)
    result = validate_rows(rows)
    assert result.valid == [sample()]
    assert result.total_count == 1
    assert not result.errors
    assert result.duplicate_count == 0
    assert rows == original


@pytest.mark.parametrize("column", ["id", "name", "email", "date", "amount", "category"])
def test_each_required_field(column):
    result = validate_rows([sample(**{column: " \t\u3000"})])
    assert not result.valid
    assert result.errors[0]["error_reason"] == f"{column}: 必須項目が空欄"


def test_duplicate_ids_include_first_occurrence_after_trimming():
    result = validate_rows([sample(id=" A "), sample(id="A"), sample(id="A"), sample(id="B")])
    assert result.duplicate_count == 3
    assert len(result.errors) == 3
    assert [row["id"] for row in result.valid] == ["B"]
    assert all("重複ID" in row["error_reason"] for row in result.errors)


def test_blank_ids_are_missing_not_duplicates_and_ids_are_case_sensitive():
    result = validate_rows([sample(id=""), sample(id=" "), sample(id="A"), sample(id="a")])
    assert result.duplicate_count == 0
    assert len(result.errors) == 2
    assert len(result.valid) == 2


@pytest.mark.parametrize("value", ["bad", "a@@example.com", "a@localhost", ".a@example.com", "a..b@example.com", "a@-example.com", "a@exam_ple.com", "a b@example.com", "あ@example.com"])
def test_invalid_email(value):
    assert not valid_email(value)
    assert "email:" in validate_rows([sample(email=value)]).errors[0]["error_reason"]


@pytest.mark.parametrize("value", ["a@example.com", "first.last+tag@sub.team.example.com", "a_b@example.org"])
def test_valid_email(value):
    assert valid_email(value)


@pytest.mark.parametrize(("value", "expected"), [("2026-9-3", "2026-09-03"), ("2026/09/03", "2026-09-03"), ("20260903", "2026-09-03"), ("2024-02-29", "2024-02-29")])
def test_date_normalization(value, expected):
    assert normalize_date(value) == expected
    assert validate_rows([sample(date=value)]).valid[0]["date"] == expected


@pytest.mark.parametrize("value", ["2026-02-29", "2026-13-01", "2026-04-31", "09/13/2026", "2026-09/13", "0000-01-01", "2026-09-13T12:00:00", "invalid"])
def test_invalid_date(value):
    assert "date:" in validate_rows([sample(date=value)]).errors[0]["error_reason"]


@pytest.mark.parametrize("value", ["abc", "NaN", "Infinity", "-inf", "1,000", "1e3", "１２３", "1_000", "￥100", "1."])
def test_invalid_amount(value):
    assert not valid_amount(value)
    assert "amount:" in validate_rows([sample(amount=value)]).errors[0]["error_reason"]


@pytest.mark.parametrize("value", ["0", "-0.10", "+12", ".5", "0001.2300", "999999999999999999999999999.01"])
def test_valid_amount_keeps_precision_and_representation(value):
    assert valid_amount(value)
    assert validate_rows([sample(amount=value)]).valid[0]["amount"] == value


def test_multiple_reasons_and_normalization_in_error_rows():
    result = validate_rows([sample(name="", email="bad", amount="oops", date="2026/9/3")])
    reason = result.errors[0]["error_reason"]
    assert all(value in reason for value in ["name:", "email:", "amount:"])
    assert reason.count(" | ") == 2
    assert result.errors[0]["date"] == "2026-09-03"


def test_empty_rows():
    assert validate_rows([]).total_count == 0


def test_email_trailing_newline_is_trimmed():
    assert validate_rows([sample(email="a@example.com\n")]).valid[0]["email"] == "a@example.com"
