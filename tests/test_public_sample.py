"""公開用の架空サンプルを、既存データに触れずCLIで検証する。"""

import csv
from pathlib import Path
import shutil
import subprocess
import sys


def test_public_sample_matches_readme(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sample = root / "samples/public/example.csv"
    original = sample.read_bytes()
    (tmp_path / "data").mkdir()
    shutil.copyfile(sample, tmp_path / "data/input.csv")
    shutil.copyfile(root / "run.py", tmp_path / "run.py")
    shutil.copytree(root / "src", tmp_path / "src")

    process = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(tmp_path / "run.py")],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert process.returncode == 1
    assert process.stderr == ""
    for expected in ("総件数: 10", "正常件数: 3", "エラー件数: 7", "重複件数: 2"):
        assert expected in process.stdout

    with (tmp_path / "output/valid.csv").open(encoding="utf-8-sig", newline="") as stream:
        valid = list(csv.DictReader(stream))
    with (tmp_path / "output/errors.csv").open(encoding="utf-8-sig", newline="") as stream:
        errors = list(csv.DictReader(stream))
    assert [row["id"] for row in valid] == ["S001", "S002", "S003"]
    assert valid[0]["name"] == "架空レコード01"
    assert valid[0]["amount"] == "1200.50"
    assert [row["date"] for row in valid] == ["2026-01-05", "2026-02-06", "2024-02-29"]
    assert len(errors) == 7
    assert sum("重複ID" in row["error_reason"] for row in errors) == 2
    by_id = {row["id"]: row["error_reason"] for row in errors}
    for row_id, field in (("E001", "name:"), ("E002", "email:"), ("E003", "date:"), ("E004", "amount:")):
        assert field in by_id[row_id]
    assert by_id["E005"].count(" | ") == 4
    assert sample.read_bytes() == original
    assert (tmp_path / "data/input.csv").read_bytes() == original
