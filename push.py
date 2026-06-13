import os
import sys
from datetime import date, datetime
from pathlib import Path

import pytz

from lark import send_lark_card, send_lark_text
from lark_card import parse_entry_to_card
from rss import extract_today_entry, fetch_rss
from state import (
    bump_failure,
    get_last_juya_entry_date,
    is_pushed_today,
    juya_silent_days,
    mark_juya_dead_alerted,
    mark_pushed_today,
    record_juya_entry_date,
    reset_failure,
    should_alert_juya_dead,
)

JUYA_DEAD_THRESHOLD_DAYS = 3

BEIJING = pytz.timezone("Asia/Shanghai")
STATE_PATH = Path(__file__).parent / "state.json"

REQUIRED_ENVS = [
    "LARK_WEBHOOK_URL",
    "LARK_WEBHOOK_SECRET",
    "LARK_OPS_WEBHOOK_URL",
    "LARK_OPS_WEBHOOK_SECRET",
]


def _log(msg: str, *, err: bool = False) -> None:
    """统一日志输出（Actions 下 stdout 非 TTY，必须 flush）。"""
    print(msg, file=sys.stderr if err else sys.stdout, flush=True)


def _today() -> date:
    """返回"今天"的日期；环境变量 PUSH_TARGET_DATE 可覆盖，用于 backfill 补发。"""
    override = os.environ.get("PUSH_TARGET_DATE", "").strip()
    if override:
        try:
            return datetime.strptime(override, "%Y-%m-%d").date()
        except ValueError as exc:
            _log(f"[error] PUSH_TARGET_DATE={override!r} 非法：{exc}", err=True)
            sys.exit(2)
    return datetime.now(BEIJING).date()


def _is_backfill() -> bool:
    return bool(os.environ.get("PUSH_TARGET_DATE", "").strip())


def _actions_run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if server and repo and run_id:
        server = server.rstrip("/")
        if not server.startswith(("http://", "https://")):
            server = "https://" + server
        return f"{server}/{repo}/actions/runs/{run_id}"
    return "(local run)"


def _check_env() -> None:
    missing = [k for k in REQUIRED_ENVS if not os.environ.get(k)]
    if missing:
        _log(f"[error] 缺少必需环境变量：{', '.join(missing)}", err=True)
        _log("[error] 请在 GitHub Actions secrets 或本地 shell 里配置后重试。", err=True)
        sys.exit(2)


def _alert_ops(ops_webhook: str, ops_secret: str, text: str) -> None:
    """向运维群告警，失败自己吞掉，避免影响主流程。"""
    try:
        send_lark_text(ops_webhook, ops_secret, text)
    except Exception as exc:
        _log(f"[warn] ops alert failed: {exc}", err=True)


def main() -> int:
    _check_env()
    webhook = os.environ["LARK_WEBHOOK_URL"]
    secret = os.environ["LARK_WEBHOOK_SECRET"]
    ops_webhook = os.environ["LARK_OPS_WEBHOOK_URL"]
    ops_secret = os.environ["LARK_OPS_WEBHOOK_SECRET"]

    today = _today()
    backfill = _is_backfill()
    real_today = datetime.now(BEIJING).date()

    # 防重复：backfill 模式下不标记 last_pushed_date，但真实今天已推过时禁止重复
    if backfill and today == real_today and is_pushed_today(STATE_PATH, real_today):
        _log("[skip] backfill 目标是今天且已推送，跳过")
        return 0
    if not backfill and is_pushed_today(STATE_PATH, today):
        _log(f"[skip] already pushed today ({today})")
        return 0

    # === 1. 拉取并解析 RSS ===
    try:
        entry = extract_today_entry(fetch_rss(), today=today)
    except Exception as exc:
        _log(f"[warn] fetch/parse failed: {exc}", err=True)
        if backfill:
            return 1
        n = bump_failure(STATE_PATH)
        if n >= 3:
            try:
                _alert_ops(ops_webhook, ops_secret,
                           f"⚠️ juya feed 拉取/解析连续 {n} 次失败\n错误：{exc}\nrun: {_actions_run_url()}")
            finally:
                try:
                    reset_failure(STATE_PATH)
                except Exception:
                    pass
        return 1

    # === 2. 今日尚无条目 — 检查 juya 是否停更 ===
    if entry is None:
        _log(f"[skip] juya not updated for {today}")
        if not backfill:
            silent = juya_silent_days(STATE_PATH, today)
            if (silent is not None and silent >= JUYA_DEAD_THRESHOLD_DAYS
                    and should_alert_juya_dead(STATE_PATH, today)):
                last_entry = get_last_juya_entry_date(STATE_PATH)
                try:
                    _alert_ops(ops_webhook, ops_secret,
                               f"⚠️ juya 已连续 {silent} 天未更新（最后一期 {last_entry}）\n"
                               f"请人工确认：https://daily.juya.uk/\nrun: {_actions_run_url()}")
                finally:
                    try:
                        mark_juya_dead_alerted(STATE_PATH, today)
                    except Exception:
                        pass
        return 0

    # === 3. 有条目 — 记录 juya 最近更新日期 ===
    pub_dt = entry.get("published_dt")
    if isinstance(pub_dt, datetime) and not backfill:
        record_juya_entry_date(STATE_PATH, pub_dt.astimezone(BEIJING).date())

    # === 4. 渲染并推送卡片 ===
    try:
        card = parse_entry_to_card(entry)
        if card is None:
            # 降级：推纯文本
            fallback_title = entry.get("title") or "<untitled>"
            fallback_link = entry.get("link") or "<no link>"
            text = (
                f"🤖 橘鸦 AI 早报 · {fallback_title}\n"
                f"（内容解析降级，请点击原文查看）\n{fallback_link}"
            )
            send_lark_text(webhook, secret, text)
            if not backfill:
                mark_pushed_today(STATE_PATH, today)
            _alert_ops(ops_webhook, ops_secret, f"⚠️ 今日内容解析降级\nrun: {_actions_run_url()}")
            _log(f"[ok] pushed (degraded) {today}")
            return 0

        send_lark_card(webhook, secret, card)
        if not backfill:
            mark_pushed_today(STATE_PATH, today)
        _log(f"[ok] pushed {today}")
        return 0

    except Exception as exc:
        if backfill:
            _log(f"[fail] backfill push failed: {exc}", err=True)
            return 1
        n = bump_failure(STATE_PATH)
        _log(f"[fail] push attempt failed ({n}/3): {exc}", err=True)
        if n >= 3:
            try:
                _alert_ops(ops_webhook, ops_secret,
                           f"⚠️ 今日推送连续 {n} 次失败\n错误：{exc}\nrun: {_actions_run_url()}")
            finally:
                try:
                    reset_failure(STATE_PATH)
                except Exception:
                    pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
