"""python -m csv_validator のCLI。"""

import argparse
from pathlib import Path
import sys

from .application import ProcessingError, run_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSVをローカルで検証し、正常行と異常行を分離します。")
    parser.add_argument("--encoding", choices=("utf-8-sig", "cp932"), default="utf-8-sig", help="入力文字コード（既定: utf-8-sig）")
    args = parser.parse_args(argv)
    try:
        run = run_project(Path(__file__).resolve().parents[2], args.encoding)
    except ProcessingError as exc:
        print(f"処理エラー: {exc}", file=sys.stderr)
        return 2
    result = run.validation
    print(f"総件数: {result.total_count}")
    print(f"正常件数: {len(result.valid)}")
    print(f"エラー件数: {len(result.errors)}")
    print(f"重複件数: {result.duplicate_count}")
    print("出力: output/valid.csv, output/errors.csv")
    print(f"ログ: logs/{run.log_path.name}")
    return 1 if result.errors else 0


def cli(argv: list[str] | None = None) -> int:
    """実際のCLI起動時だけ出力をUTF-8にする。main()の呼び出し元は変更しない。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
        # StringIO等、再設定機能のないホスト提供ストリームはそのまま使用する。
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(cli())
