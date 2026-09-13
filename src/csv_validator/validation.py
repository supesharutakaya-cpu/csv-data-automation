"""ファイル操作から独立した検証ルール。"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re


REQUIRED_COLUMNS = ("id", "name", "email", "date", "amount", "category")
_LOCAL_PART = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+")
_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")
_DATE = re.compile(r"([0-9]{4})([-/])([0-9]{1,2})\2([0-9]{1,2})")


@dataclass(frozen=True)
class ValidationResult:
    valid: list[dict[str, str]]
    errors: list[dict[str, str]]
    duplicate_count: int

    @property
    def total_count(self) -> int:
        return len(self.valid) + len(self.errors)


def valid_email(value: str) -> bool:
    """一般的なASCIIメール形式のみ。DNS照会やメール送信は行わない。"""
    if len(value) > 254 or value.count("@") != 1:
        return False
    local, domain = value.split("@")
    labels = domain.split(".")
    return bool(
        0 < len(local) <= 64
        and _LOCAL_PART.fullmatch(local)
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
        and len(labels) >= 2
        and all(_DOMAIN_LABEL.fullmatch(label) for label in labels)
        and re.fullmatch(r"[A-Za-z]{2,63}", labels[-1])
    )


def normalize_date(value: str) -> str:
    """年先頭のハイフン/スラッシュ区切り、または8桁の日付。"""
    match = _DATE.fullmatch(value)
    if match:
        year, _, month, day = match.groups()
    elif re.fullmatch(r"[0-9]{8}", value):
        year, month, day = value[:4], value[4:6], value[6:]
    else:
        raise ValueError("unsupported date format")
    return date(int(year), int(month), int(day)).isoformat()


def valid_amount(value: str) -> bool:
    if not _NUMBER.fullmatch(value):
        return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def validate_rows(rows: list[dict[str, str]]) -> ValidationResult:
    """空白除去後に検証する。引数を変更せず、重複IDは全該当行を除外する。"""
    cleaned = [{key: value.strip() for key, value in row.items()} for row in rows]
    counts = Counter(row["id"] for row in cleaned if row["id"])
    valid: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    duplicate_count = 0
    for row in cleaned:
        reasons = [f"{key}: 必須項目が空欄" for key in REQUIRED_COLUMNS if not row[key]]
        if row["id"] and counts[row["id"]] > 1:
            reasons.append("id: 重複ID")
            duplicate_count += 1
        if row["email"] and not valid_email(row["email"]):
            reasons.append("email: メールアドレスの形式が不正")
        if row["date"]:
            try:
                row["date"] = normalize_date(row["date"])
            except ValueError:
                reasons.append("date: 日付の形式または日付が不正")
        if row["amount"] and not valid_amount(row["amount"]):
            reasons.append("amount: 有効な数値ではありません")
        if reasons:
            errors.append({**row, "error_reason": " | ".join(reasons)})
        else:
            valid.append(row)
    return ValidationResult(valid, errors, duplicate_count)
