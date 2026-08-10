import base64
import hashlib
import hmac
import json
import time
from typing import Any, Mapping

import requests

USER_AGENT = "Ainews-to-Feishu/1.0 (+https://github.com/Ai-luren/Ainews-to-Feishu)"

# 飞书 webhook 频率限制：同一 webhook 1 分钟内最多 5 条消息。
# 超过会返回 code=11232 msg="frequency limited"。
# 限流后等待 30 秒重试，最多重试 2 次。
_RATE_LIMIT_CODE = 11232
_RATE_LIMIT_RETRIES = 2
_RATE_LIMIT_WAIT = 30  # 秒

# 网络异常重试（ConnectionError / Timeout / 5xx），backoff: 5s, 15s
_NETWORK_RETRIES = 2
_NETWORK_BACKOFFS = [5, 15]

# 飞书卡片请求体限制 30KB，留 2KB 余量给 timestamp/sign 外层
_MAX_CARD_BYTES = 28000


def _session() -> requests.Session:
    """单次 HTTP session（不做 POST 自动重试，避免非幂等请求重复推送）。"""
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def lark_sign(secret: str, timestamp: int) -> str:
    """飞书自定义机器人签名。

    算法（按飞书官方）：key = f"{timestamp}\n{secret}"，msg 为空，HMAC-SHA256 → base64。

    防御：
    - timestamp 必须是整数秒。传 float 会拼出 "1609459200.0" 导致签名失败。
    - secret 为空会退化为固定哈希（不安全），显式拒绝。
    """
    if not isinstance(timestamp, (int, float)):
        raise TypeError(f"timestamp must be int/float, got {type(timestamp).__name__}")
    if not secret:
        raise ValueError("secret must not be empty")
    # 强制整数化，防止误传 time.time()（float）时签名静默出错
    ts_int = int(timestamp)
    key = f"{ts_int}\n{secret}".encode("utf-8")
    digest = hmac.new(
        key=key,
        msg=b"",
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _post_json(webhook: str, payload: Mapping[str, Any], timeout: int) -> Mapping[str, Any]:
    """共用的飞书 webhook POST：处理非 200 / 非 JSON / 业务 code != 0 三种失败。

    重试策略（独立计数器，互不挤占）：
    - 频率限制（code=11232）：等待 30s 重试，最多 2 次
    - UnicodeEncodeError：等待 2s 重试，最多 2 次
    - 网络异常（ConnectionError / Timeout / 5xx）：backoff 5s/15s，最多 2 次
    """
    if not webhook or not isinstance(webhook, str) or not webhook.startswith(("http://", "https://")):
        raise ValueError(f"invalid webhook (scheme not http/https, got: {str(webhook)[:30]!r}...)")

    rate_limit_retries = 0
    encode_retries = 0
    network_retries = 0
    while True:
        try:
            with _session() as s:
                resp = s.post(webhook, json=payload, timeout=timeout)
        except UnicodeEncodeError as e:
            if encode_retries < _RATE_LIMIT_RETRIES:
                encode_retries += 1
                print(f"[lark] UnicodeEncodeError, 重试 ({encode_retries}/{_RATE_LIMIT_RETRIES}): {e}", flush=True)
                time.sleep(2)
                continue
            raise RuntimeError(f"lark 请求编码错误（重试已用完）: {e}") from e
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if network_retries < _NETWORK_RETRIES:
                backoff = _NETWORK_BACKOFFS[network_retries]
                network_retries += 1
                print(f"[lark] 网络异常, {backoff}s 后重试 ({network_retries}/{_NETWORK_RETRIES}): {e}", flush=True)
                time.sleep(backoff)
                continue
            raise RuntimeError(f"lark 网络异常（重试已用完）: {e}") from e

        if 500 <= resp.status_code < 600:
            if network_retries < _NETWORK_RETRIES:
                backoff = _NETWORK_BACKOFFS[network_retries]
                network_retries += 1
                print(f"[lark] HTTP {resp.status_code}, {backoff}s 后重试 ({network_retries}/{_NETWORK_RETRIES})", flush=True)
                time.sleep(backoff)
                continue
            raise RuntimeError(f"lark http {resp.status_code}（重试已用完）: {resp.text[:200]}")

        if resp.status_code != 200:
            raise RuntimeError(f"lark http {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise RuntimeError(f"lark 响应不是 JSON（http 200 但 body={resp.text[:200]!r}）") from e

        if not isinstance(data, dict):
            raise RuntimeError(f"lark 响应不是 dict（是 {type(data).__name__}）: {str(data)[:200]}")
        if data.get("code", -1) != 0:
            # 频率限制：等待后重试
            if data.get("code") == _RATE_LIMIT_CODE and rate_limit_retries < _RATE_LIMIT_RETRIES:
                rate_limit_retries += 1
                print(f"[lark] 频率限制，{_RATE_LIMIT_WAIT}s 后重试 ({rate_limit_retries}/{_RATE_LIMIT_RETRIES})", flush=True)
                time.sleep(_RATE_LIMIT_WAIT)
                continue
            raise RuntimeError(f"lark error code={data.get('code')} msg={data.get('msg')}")
        return data


def send_lark_text(webhook: str, secret: str, text: str, timeout: int = 10) -> None:
    """推一条纯文本到飞书自定义机器人。失败抛 RuntimeError。"""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    timestamp = int(time.time())
    payload: Mapping[str, Any] = {
        "timestamp": str(timestamp),
        "sign": lark_sign(secret, timestamp),
        "msg_type": "text",
        "content": {"text": text},
    }
    _post_json(webhook, payload, timeout)


def _fit_card_size(card: Mapping[str, Any], sign: str, timestamp: int, max_bytes: int) -> Mapping[str, Any]:
    """如果卡片 payload 超过 max_bytes，从尾部截断 elements 并附加截断提示。"""
    def _payload_size(c: Mapping[str, Any]) -> int:
        p = {"timestamp": str(timestamp), "sign": sign, "msg_type": "interactive", "card": c}
        return len(json.dumps(p, ensure_ascii=False).encode("utf-8"))

    if _payload_size(card) <= max_bytes:
        return card

    elements = list(card.get("elements", []))
    target = max_bytes - 200  # 留余量给截断提示
    while elements and _payload_size({**card, "elements": elements}) > target:
        elements.pop()

    notice = {"tag": "div", "text": {"tag": "lark_md", "content": "⚠️ 内容过长，已截断部分条目"}}
    if not elements:
        return {**card, "elements": [notice]}
    elements.append(notice)
    return {**card, "elements": elements}


def send_lark_card(webhook: str, secret: str, card: Mapping[str, Any], timeout: int = 10) -> None:
    """推一张 interactive 卡片到飞书。失败抛 RuntimeError。

    自动检查卡片大小，超过飞书 30KB 限制时截断 elements 列表。
    """
    if not isinstance(card, dict) or not card:
        raise ValueError("card must be a non-empty dict")
    timestamp = int(time.time())
    sign = lark_sign(secret, timestamp)
    card = _fit_card_size(card, sign, timestamp, _MAX_CARD_BYTES)
    payload: Mapping[str, Any] = {
        "timestamp": str(timestamp),
        "sign": sign,
        "msg_type": "interactive",
        "card": card,
    }
    _post_json(webhook, payload, timeout)
