"""仮想環境を有効化せずに実行できる入口。"""

from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from csv_validator.__main__ import cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(cli())
