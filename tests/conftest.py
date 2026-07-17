"""共享 fixture 和工具函数，消除跨文件重复。"""
import json
from datetime import datetime
from pathlib import Path

import pytest
import pytz

BEIJING = pytz.timezone("Asia/Shanghai")

# push 测试用的常量
FAKE_PUB = datetime(2026, 4, 27, 1, 0, tzinfo=pytz.utc)

ENV_MORNING = {
    "LARK_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/main",
    "LARK_WEBHOOK_SECRET": "s1",
    "LARK_OPS_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/ops",
    "LARK_OPS_WEBHOOK_SECRET": "s2",
    "PUSH_MODE": "morning",
}

ENV_ALL = {**ENV_MORNING, "PUSH_MODE": "all"}


def fake_datetime(hour, minute=0):
    """构造假的 push.datetime，now() 返回北京时间 hour:minute。"""
    fake_now = datetime(2026, 4, 27, hour, minute, tzinfo=BEIJING)
    return type("FakeDT", (), {
        "now": staticmethod(lambda tz=None: fake_now),
        "strptime": staticmethod(datetime.strptime),
    })


@pytest.fixture
def state_path(tmp_path, monkeypatch):
    """隔离 state.json，避免污染仓库真实状态。"""
    import push
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"last_pushed_date": None, "consecutive_failures": 0}))
    monkeypatch.setattr(push, "STATE_PATH", p)
    return p
