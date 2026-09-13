"""プロジェクト内に限定したCSV読み書きと、個人情報を含めないログ。"""

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
from uuid import uuid4

from .validation import REQUIRED_COLUMNS, ValidationResult, validate_rows


class ProcessingError(Exception):
    """利用者へ表示してよい、CSV値を含まない処理エラー。"""


@dataclass(frozen=True)
class RunResult:
    validation: ValidationResult
    log_path: Path


def safe_path(root: Path, relative: str) -> Path:
    """リンク経由の外部書き込みと既存ハードリンクの更新を拒否する。"""
    candidate = root / relative
    if not candidate.resolve().is_relative_to(root):
        raise ProcessingError("安全確認: プロジェクト外へのパスは使用できません。")
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ProcessingError("安全確認: リンクされたパスは使用できません。")
        if current.is_file() and current.stat().st_nlink > 1:
            raise ProcessingError("安全確認: ハードリンクされたファイルは使用できません。")
    return candidate


def read_csv(path: Path, encoding: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding=encoding, newline="") as stream:
            reader = csv.reader(stream, strict=True)
            raw_header = next(reader, None)
            if not raw_header:
                raise ProcessingError("CSVが空です。必須列を含むヘッダーが必要です。")
            header = [item.strip() for item in raw_header]
            if any(not item for item in header) or len(set(header)) != len(header):
                raise ProcessingError("ヘッダーに空の列名または重複した列名があります。")
            missing = [key for key in REQUIRED_COLUMNS if key not in header]
            if missing:
                raise ProcessingError("必要列が不足しています: " + ", ".join(missing))
            if "error_reason" in header:
                raise ProcessingError("error_reasonは出力用の予約列です。入力には使用できません。")
            rows = []
            for values in reader:
                if not values:  # 完全な空行のみスキップする。空欄レコードは検証対象。
                    continue
                if len(values) != len(header):
                    raise ProcessingError(
                        f"CSVの列数が一致しません（物理行 {reader.line_num} 付近）。"
                    )
                rows.append(dict(zip(header, values, strict=True)))
            return header, rows
    except UnicodeError:
        raise ProcessingError("文字コードを読み取れません。--encoding を確認してください。") from None
    except csv.Error:
        raise ProcessingError("CSV構造が不正、またはフィールドが読み取り上限を超えています。") from None


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def processing_lock(root: Path):
    """同時実行を拒否。自分で新規作成したロックだけを終了時に解放する。"""
    lock_path = safe_path(root, "logs/.csv-validator.lock")
    try:
        stream = lock_path.open("x", encoding="ascii")
    except FileExistsError:
        raise ProcessingError("別の処理が実行中、または前回のロックが残っています。READMEを確認してください。") from None
    try:
        with stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock_path.unlink()


def publish_outputs(root: Path, header: list[str], result: ValidationResult, run_id: str) -> None:
    """2出力を事前作成し、以前の出力を保存して置換。通常のI/O失敗時は復元。"""
    output = safe_path(root, "output")
    output.mkdir(exist_ok=True)
    targets = [safe_path(root, f"output/{name}") for name in ("valid.csv", "errors.csv")]
    if any(path.exists() and not path.is_file() for path in targets):
        raise ProcessingError("出力先に同名のフォルダーがあります。")
    runs = safe_path(root, "output/.runs")
    runs.mkdir(exist_ok=True)
    staging = safe_path(root, f"output/.runs/{run_id}")
    staging.mkdir()
    staged = [staging / "valid.csv", staging / "errors.csv"]
    write_csv(staged[0], header, result.valid)
    write_csv(staged[1], [*header, "error_reason"], result.errors)
    backups: dict[Path, Path] = {}
    for target in targets:
        if target.exists():
            backup = staging / (target.name + ".previous")
            shutil.copyfile(target, backup)
            backups[target] = backup
    replaced: list[Path] = []
    try:
        for source, target in zip(staged, targets, strict=True):
            os.replace(source, target)
            replaced.append(target)
    except OSError:
        try:
            for target in reversed(replaced):
                if target in backups:
                    restore = staging / (target.name + ".restore")
                    shutil.copyfile(backups[target], restore)
                    os.replace(restore, target)
                else:
                    target.unlink()  # この実行が新規作成した出力だけを取り消す。
        except OSError:
            raise ProcessingError("出力更新と復元に失敗しました。output/.runsのバックアップを確認してください。") from None
        raise ProcessingError("出力更新に失敗しました。以前の出力を保持しました。Excelなどで閉じて再実行してください。") from None


def run_project(root: Path, encoding: str = "utf-8-sig") -> RunResult:
    if encoding not in ("utf-8-sig", "cp932"):
        raise ProcessingError("対応文字コードはutf-8-sigとcp932です。")
    root = root.resolve(strict=True)
    logger = logging.getLogger(f"csv_validator.{uuid4().hex}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = None
    try:
        logs = safe_path(root, "logs")
        logs.mkdir(exist_ok=True)
        with processing_lock(root):
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid4().hex
            log_path = safe_path(root, f"logs/validation_{run_id}.log")
            handler = logging.FileHandler(log_path, mode="x", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            logger.info("処理開始 encoding=%s", encoding)
            try:
                source = safe_path(root, "data/input.csv")
                header, rows = read_csv(source, encoding)
                result = validate_rows(rows)
                publish_outputs(root, header, result, run_id)
                logger.info(
                    "処理完了 総件数=%d 正常件数=%d エラー件数=%d 重複件数=%d",
                    result.total_count, len(result.valid), len(result.errors), result.duplicate_count,
                )
                return RunResult(result, log_path)
            except ProcessingError as exc:
                logger.error("処理中止: %s", exc)
                raise
            except OSError as exc:
                logger.error("ファイル操作失敗 種類=%s", type(exc).__name__)
                raise
    except OSError:
        raise ProcessingError("ファイルを読み書きできません。入力の存在、アクセス権、空き容量、Excelで開いていないかを確認してください。") from None
    finally:
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()
