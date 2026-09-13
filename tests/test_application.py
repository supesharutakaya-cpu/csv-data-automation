import csv
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys

import pytest

from csv_validator import application
from csv_validator.__main__ import main
from csv_validator.application import ProcessingError, run_project
from csv_validator.validation import REQUIRED_COLUMNS


HEADER = ",".join(REQUIRED_COLUMNS)
ROW = "001,架空担当,test@example.com,2026/9/13,100.50,備品"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/input.csv").write_text(HEADER + "\n" + ROW + "\n", encoding="utf-8")
    return tmp_path


def read_output(project, name):
    with (project / "output" / name).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        return reader.fieldnames, rows


def test_end_to_end_input_unchanged_bom_and_private_logs(project):
    source = project / "data/input.csv"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    result = run_project(project)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert result.validation.total_count == 1
    header, valid = read_output(project, "valid.csv")
    assert header == list(REQUIRED_COLUMNS)
    assert valid[0]["id"] == "001"
    assert valid[0]["date"] == "2026-09-13"
    assert read_output(project, "errors.csv") == ([*REQUIRED_COLUMNS, "error_reason"], [])
    assert (project / "output/valid.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    log = result.log_path.read_text(encoding="utf-8")
    assert "総件数=1" in log
    assert "test@example.com" not in log
    assert "架空担当" not in log
    assert not (project / "logs/.csv-validator.lock").exists()


def test_mixed_rows_and_counts(project):
    (project / "data/input.csv").write_text(HEADER + "\n" + ROW + "\n" + ROW.replace("001,", "002,").replace("100.50", "bad") + "\n", encoding="utf-8")
    result = run_project(project).validation
    assert (result.total_count, len(result.valid), len(result.errors)) == (2, 1, 1)
    assert "amount:" in read_output(project, "errors.csv")[1][0]["error_reason"]


@pytest.mark.parametrize("content", ["", "\ufeff", "\n", "id,name\n1,example\n", HEADER + ",id\n", HEADER + ",error_reason\n", HEADER + ",\n", HEADER + "\n1,too,few\n", HEADER + "\n" + ROW + ",extra\n", HEADER + '\n1,"unclosed'])
def test_bad_file_preserves_previous_outputs_and_logs_failure(project, content):
    run_project(project)
    previous = [(project / "output" / name).read_bytes() for name in ["valid.csv", "errors.csv"]]
    (project / "data/input.csv").write_text(content, encoding="utf-8")
    with pytest.raises(ProcessingError):
        run_project(project)
    assert [(project / "output" / name).read_bytes() for name in ["valid.csv", "errors.csv"]] == previous
    assert any("処理中止" in path.read_text(encoding="utf-8") for path in (project / "logs").glob("*.log"))


def test_header_only_and_blank_lines(project):
    (project / "data/input.csv").write_text(HEADER + "\n\n", encoding="utf-8")
    result = run_project(project).validation
    assert result.total_count == 0
    assert read_output(project, "valid.csv")[1] == []
    assert read_output(project, "errors.csv")[1] == []


def test_blank_record_is_error(project):
    (project / "data/input.csv").write_text(HEADER + "\n,,,,,\n", encoding="utf-8")
    result = run_project(project).validation
    assert result.total_count == 1
    assert result.errors[0]["error_reason"].count("必須項目") == 6


def test_cp932_and_wrong_encoding(project):
    (project / "data/input.csv").write_bytes((HEADER + "\n" + ROW).encode("cp932"))
    with pytest.raises(ProcessingError, match="文字コード"):
        run_project(project)
    assert len(run_project(project, "cp932").validation.valid) == 1


def test_bom_header_trim_extra_column_quoted_comma_and_newline(project):
    with (project / "data/input.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([f" {key} " for key in REQUIRED_COLUMNS] + ["notes"])
        writer.writerow(["001", " 架空,\n担当 ", "test@example.com", "20260913", "10", "備品", " メモ "])
    run_project(project)
    header, rows = read_output(project, "valid.csv")
    assert header[-1] == "notes"
    assert rows[0]["notes"] == "メモ"
    assert rows[0]["name"] == "架空,\n担当"


def test_rerun_backs_up_existing_outputs(project):
    run_project(project)
    previous = (project / "output/valid.csv").read_bytes()
    run_project(project)
    backups = list((project / "output/.runs").glob("*/valid.csv.previous"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == previous


@pytest.mark.parametrize("existing", [True, False])
def test_second_replace_failure_rolls_back(project, monkeypatch, existing):
    if existing:
        run_project(project)
    target = project / "output/valid.csv"
    previous = target.read_bytes() if existing else None
    real_replace = application.os.replace

    def fail_second(source, destination):
        if Path(destination).name == "errors.csv":
            raise PermissionError("simulated lock")
        return real_replace(source, destination)

    monkeypatch.setattr(application.os, "replace", fail_second)
    with pytest.raises(ProcessingError, match="以前の出力"):
        run_project(project)
    assert target.read_bytes() == previous if existing else not target.exists()


def test_staging_write_failure_keeps_previous_outputs(project, monkeypatch):
    run_project(project)
    previous = (project / "output/valid.csv").read_bytes()

    def fail_write(*args):
        raise OSError("simulated disk full")

    monkeypatch.setattr(application, "write_csv", fail_write)
    with pytest.raises(ProcessingError):
        run_project(project)
    assert (project / "output/valid.csv").read_bytes() == previous


def test_concurrent_run_is_rejected_and_existing_lock_is_preserved(project):
    (project / "logs").mkdir()
    lock = project / "logs/.csv-validator.lock"
    lock.write_text("test-lock", encoding="ascii")
    with pytest.raises(ProcessingError, match="ロック"):
        run_project(project)
    assert lock.read_text() == "test-lock"


def test_hardlinked_output_rejected_without_changing_input(project):
    (project / "output").mkdir()
    source = project / "data/input.csv"
    before = source.read_bytes()
    os.link(source, project / "output/valid.csv")
    with pytest.raises(ProcessingError, match="ハードリンク"):
        run_project(project)
    assert source.read_bytes() == before


def test_outside_path_rejected_without_writing(project):
    with pytest.raises(ProcessingError, match="プロジェクト外"):
        application.safe_path(project.resolve(), "../outside.csv")


def test_linked_directory_rejected(project, monkeypatch):
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda path: path.name == "output" or original(path))
    with pytest.raises(ProcessingError, match="リンク"):
        run_project(project)


def test_missing_input_is_handled(project):
    empty = project / "empty-project"
    empty.mkdir()
    with pytest.raises(ProcessingError, match="入力の存在"):
        run_project(empty)


@pytest.mark.parametrize(("has_errors", "expected"), [(False, 0), (True, 1)])
def test_cli_summary_and_exit_status(project, monkeypatch, capsys, has_errors, expected):
    if has_errors:
        (project / "data/input.csv").write_text(HEADER + "\n" + ROW.replace("100.50", "bad"), encoding="utf-8")
    monkeypatch.setattr("csv_validator.__main__.run_project", lambda root, encoding: run_project(project, encoding))
    assert main([]) == expected
    captured = capsys.readouterr()
    assert all(label in captured.out for label in ["総件数: 1", "正常件数:", "エラー件数:", "重複件数: 0"])
    assert "test@example.com" not in captured.out


def test_cli_processing_failure(project, monkeypatch, capsys):
    def fail(*args):
        raise ProcessingError("CSVが空です。")

    monkeypatch.setattr("csv_validator.__main__.run_project", fail)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    assert main([]) == 2
    assert sys.stdout is original_stdout and sys.stderr is original_stderr
    assert "CSVが空です" in capsys.readouterr().err

    # CLI専用ラッパーも、reconfigureがない/呼び出せない捕捉ストリームで動く。
    from csv_validator.__main__ import cli

    class HostCapture(io.StringIO):
        reconfigure = None

    for capture_type in (io.StringIO, HostCapture):
        stdout, stderr = capture_type(), capture_type()
        with monkeypatch.context() as capture_patch:
            capture_patch.setattr(sys, "stdout", stdout)
            capture_patch.setattr(sys, "stderr", stderr)
            with pytest.raises(SystemExit) as help_exit:
                cli(["--help"])
            assert help_exit.value.code == 0
            assert "入力文字コード" in stdout.getvalue()
            assert cli([]) == 2
            assert "処理エラー: CSVが空です。" in stderr.getvalue()
            assert not stdout.closed and not stderr.closed

    # 実際のTextIOWrapperを使う子プロセスでもstderrがUTF-8になることを確認。
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONUTF8"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    script = (
        "import csv_validator.__main__ as command\n"
        "from csv_validator.application import ProcessingError\n"
        "def fail(*args):\n"
        "    raise ProcessingError('CSVが空です。')\n"
        "command.run_project = fail\n"
        "raise SystemExit(command.cli([]))\n"
    )
    process = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=project, env=env, capture_output=True, check=False,
    )
    assert process.returncode == 2, process.stderr
    assert process.stdout == b""
    assert process.stderr.decode("utf-8").strip() == "処理エラー: CSVが空です。"


def test_windows_entrypoint_help_from_other_directory(project):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONUTF8"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(root / "src")
    # 親pytestのUTF-8設定に依存せず、両方のCLI入口を検証する。
    for entrypoint in ([str(root / "run.py")], ["-m", "csv_validator"]):
        process = subprocess.run(
            [sys.executable, "-B", *entrypoint, "--help"],
            cwd=project,
            env=env,
            capture_output=True,
            check=False,
        )
        assert process.returncode == 0, process.stderr
        assert process.stderr == b""
        help_text = process.stdout.decode("utf-8")
        assert "--encoding" in help_text
        assert "入力文字コード" in help_text
        assert "CSVをローカルで検証し" in help_text
