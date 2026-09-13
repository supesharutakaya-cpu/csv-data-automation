"""テストの一時ファイルもプロジェクト内に限定する。"""
from pathlib import Path
from uuid import uuid4


def pytest_configure(config):
    # 既存basetempを削除しないよう、毎回新しいフォルダーを指定する。
    parent = Path(__file__).resolve().parents[1] / '.test-tmp'
    parent.mkdir(exist_ok=True)
    config.option.basetemp = str(parent / uuid4().hex)
