"""阶段2修复的测试覆盖。

测试内容：
1. aihot 日期不匹配路径的停更告警（新增 _handle_dead_alert 调用）
2. builders 日期不匹配路径的停更告警（新增 _handle_dead_alert 调用）
3. record_last_run 时区一致性（datetime.now(BEIJING) 替代 datetime.now()）
"""
import json
from datetime import date

import pytest

import push
from state import record_last_run


# ---------------------------------------------------------------------------
# aihot 日期不匹配 → 停更告警
# ---------------------------------------------------------------------------

def test_aihot_date_mismatch_triggers_dead_alert(state_path, monkeypatch):
    """aihot 日期不匹配 + 连续 4 天未更新 → 触发停更告警。"""
    state_path.write_text(json.dumps({
        "aihot_pushed_date": None,
        "aihot_failures": 0,
        "last_aihot_entry_date": "2026-04-24",
        "aihot_dead_alerted_on": None,
    }))

    today = date(2026, 4, 28)
    monkeypatch.setattr(push, "_today", lambda: today)

    old_daily = {"date": "2026-04-27", "sections": [{"label": "t", "items": [{"title": "t"}]}]}
    monkeypatch.setattr(push, "fetch_daily", lambda *a, **kw: old_daily)
    monkeypatch.setattr(push, "has_content", lambda d: True)
    monkeypatch.setattr(push, "daily_date", lambda d: date(2026, 4, 27))
    monkeypatch.setattr(push, "total_items", lambda d: 1)

    alerts = []
    monkeypatch.setattr(push, "send_lark_text",
                        lambda url, secret, text: alerts.append((url, text)))
    monkeypatch.setattr(push, "send_lark_card", lambda *a, **kw: None)

    result = push._push_aihot(
        "main_wh", "main_secret", "ops_wh", "ops_secret", today, False
    )

    assert result is True
    ops_alerts = [a for a in alerts if a[0] == "ops_wh"]
    assert len(ops_alerts) == 1
    assert "aihot" in ops_alerts[0][1]
    assert "4 天未更新" in ops_alerts[0][1]


def test_aihot_date_mismatch_no_alert_when_recent(state_path, monkeypatch):
    """aihot 日期不匹配 + 仅 1 天未更新 → 不触发停更告警。"""
    state_path.write_text(json.dumps({
        "aihot_pushed_date": None,
        "aihot_failures": 0,
        "last_aihot_entry_date": "2026-04-27",
        "aihot_dead_alerted_on": None,
    }))

    today = date(2026, 4, 28)
    monkeypatch.setattr(push, "_today", lambda: today)

    old_daily = {"date": "2026-04-27", "sections": [{"label": "t", "items": [{"title": "t"}]}]}
    monkeypatch.setattr(push, "fetch_daily", lambda *a, **kw: old_daily)
    monkeypatch.setattr(push, "has_content", lambda d: True)
    monkeypatch.setattr(push, "daily_date", lambda d: date(2026, 4, 27))
    monkeypatch.setattr(push, "total_items", lambda d: 1)

    alerts = []
    monkeypatch.setattr(push, "send_lark_text",
                        lambda url, secret, text: alerts.append((url, text)))
    monkeypatch.setattr(push, "send_lark_card", lambda *a, **kw: None)

    result = push._push_aihot(
        "main_wh", "main_secret", "ops_wh", "ops_secret", today, False
    )

    assert result is True
    ops_alerts = [a for a in alerts if a[0] == "ops_wh"]
    assert len(ops_alerts) == 0


def test_aihot_date_mismatch_no_duplicate_alert(state_path, monkeypatch):
    """aihot 日期不匹配 + 已告警过 → 同一天不重复告警。"""
    state_path.write_text(json.dumps({
        "aihot_pushed_date": None,
        "aihot_failures": 0,
        "last_aihot_entry_date": "2026-04-24",
        "aihot_dead_alerted_on": "2026-04-28",
    }))

    today = date(2026, 4, 28)
    monkeypatch.setattr(push, "_today", lambda: today)

    old_daily = {"date": "2026-04-27", "sections": [{"label": "t", "items": [{"title": "t"}]}]}
    monkeypatch.setattr(push, "fetch_daily", lambda *a, **kw: old_daily)
    monkeypatch.setattr(push, "has_content", lambda d: True)
    monkeypatch.setattr(push, "daily_date", lambda d: date(2026, 4, 27))
    monkeypatch.setattr(push, "total_items", lambda d: 1)

    alerts = []
    monkeypatch.setattr(push, "send_lark_text",
                        lambda url, secret, text: alerts.append((url, text)))
    monkeypatch.setattr(push, "send_lark_card", lambda *a, **kw: None)

    result = push._push_aihot(
        "main_wh", "main_secret", "ops_wh", "ops_secret", today, False
    )

    assert result is True
    ops_alerts = [a for a in alerts if a[0] == "ops_wh"]
    assert len(ops_alerts) == 0


# ---------------------------------------------------------------------------
# builders 日期不匹配 → 停更告警
# ---------------------------------------------------------------------------

def test_builders_date_mismatch_triggers_dead_alert(state_path, monkeypatch):
    """builders 日期不匹配 + 连续 4 天未更新 → 触发停更告警。"""
    state_path.write_text(json.dumps({
        "builders_pushed_date": None,
        "builders_failures": 0,
        "last_builders_entry_date": "2026-04-24",
        "builders_dead_alerted_on": None,
    }))

    today = date(2026, 4, 28)
    monkeypatch.setattr(push, "_today", lambda: today)

    old_daily = {
        "date": date(2026, 4, 27),
        "tweets": [{"name": "test", "text": "hello", "engagement": 100}],
    }
    monkeypatch.setattr(push, "builders_fetch_daily", lambda: old_daily)

    alerts = []
    monkeypatch.setattr(push, "send_lark_text",
                        lambda url, secret, text: alerts.append((url, text)))
    monkeypatch.setattr(push, "send_lark_card", lambda *a, **kw: None)

    result = push._push_builders(
        "main_wh", "main_secret", "ops_wh", "ops_secret", today, False
    )

    assert result is True
    ops_alerts = [a for a in alerts if a[0] == "ops_wh"]
    assert len(ops_alerts) == 1
    assert "follow-builders" in ops_alerts[0][1]
    assert "4 天未更新" in ops_alerts[0][1]


def test_builders_date_mismatch_no_alert_when_recent(state_path, monkeypatch):
    """builders 日期不匹配 + 仅 1 天未更新 → 不触发停更告警。"""
    state_path.write_text(json.dumps({
        "builders_pushed_date": None,
        "builders_failures": 0,
        "last_builders_entry_date": "2026-04-27",
        "builders_dead_alerted_on": None,
    }))

    today = date(2026, 4, 28)
    monkeypatch.setattr(push, "_today", lambda: today)

    old_daily = {
        "date": date(2026, 4, 27),
        "tweets": [{"name": "test", "text": "hello", "engagement": 100}],
    }
    monkeypatch.setattr(push, "builders_fetch_daily", lambda: old_daily)

    alerts = []
    monkeypatch.setattr(push, "send_lark_text",
                        lambda url, secret, text: alerts.append((url, text)))
    monkeypatch.setattr(push, "send_lark_card", lambda *a, **kw: None)

    result = push._push_builders(
        "main_wh", "main_secret", "ops_wh", "ops_secret", today, False
    )

    assert result is True
    ops_alerts = [a for a in alerts if a[0] == "ops_wh"]
    assert len(ops_alerts) == 0


# ---------------------------------------------------------------------------
# record_last_run 时区一致性
# ---------------------------------------------------------------------------

def test_record_last_run_uses_beijing_timezone(tmp_path):
    """record_last_run 应使用北京时间（+08:00 时区偏移）。"""
    p = tmp_path / "state.json"
    p.write_text("{}")
    record_last_run(p, status="ok")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["last_run_at"] is not None
    assert "+08:00" in data["last_run_at"]


def test_record_last_run_failed_with_beijing_timezone(tmp_path):
    """record_last_run(failed) 也应使用北京时间。"""
    p = tmp_path / "state.json"
    p.write_text("{}")
    record_last_run(p, status="failed", error="test")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "+08:00" in data["last_run_at"]
