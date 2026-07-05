"""lark 模块完整测试：签名、文本推送、卡片推送、频率限制重试。

合并自 test_lark_sign / test_send_lark_text / test_send_lark_card /
test_lark_send / test_lark_rate_limit 五个文件，删除 4 个重复用例。
"""
import json
from unittest.mock import patch

import pytest
import responses

from lark import (
    _post_json,
    lark_sign,
    send_lark_card,
    send_lark_text,
)

WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test"
SECRET = "sec"
CARD = {"header": {"title": {"tag": "plain_text", "content": "t"}},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "x"}}]}


# ---------------------------------------------------------------------------
# 签名
# ---------------------------------------------------------------------------

def test_lark_sign_known_vector():
    result = lark_sign("test_secret", 1609459200)
    assert result == "qVbqb8D2J+M/bRkXvbE6oxwqeW951L1/HLlrNo1pY0g="


def test_lark_sign_returns_base64_str():
    result = lark_sign("any_secret", 1700000000)
    assert isinstance(result, str)
    assert "\n" not in result and " " not in result


def test_lark_sign_rejects_empty_secret():
    with pytest.raises(ValueError):
        lark_sign("", 1700000000)


def test_lark_sign_rejects_non_numeric_timestamp():
    with pytest.raises(TypeError):
        lark_sign("secret", "not-a-number")


# ---------------------------------------------------------------------------
# send_lark_text: 成功路径
# ---------------------------------------------------------------------------

@responses.activate
def test_send_lark_text_sends_json_with_sign():
    responses.add(responses.POST, WEBHOOK, status=200, json={"code": 0, "msg": "ok"})
    send_lark_text(WEBHOOK, "secret", "hello")
    body = json.loads(responses.calls[0].request.body)
    assert body["msg_type"] == "text"
    assert body["content"] == {"text": "hello"}
    assert "sign" in body and body["sign"]


# ---------------------------------------------------------------------------
# send_lark_card: 成功路径
# ---------------------------------------------------------------------------

@responses.activate
def test_send_lark_card_success():
    responses.add(responses.POST, WEBHOOK, json={"code": 0, "msg": "ok"}, status=200)
    send_lark_card(WEBHOOK, SECRET, CARD)
    body = json.loads(responses.calls[0].request.body)
    assert body["msg_type"] == "interactive"
    assert body["card"] == CARD
    assert "timestamp" in body and "sign" in body


# ---------------------------------------------------------------------------
# HTTP 非 200
# ---------------------------------------------------------------------------

@responses.activate
def test_send_lark_text_http_400_raises():
    responses.add(responses.POST, WEBHOOK, status=400, body="bad request")
    with pytest.raises(RuntimeError):
        send_lark_text(WEBHOOK, "secret", "hi")


@responses.activate
def test_send_lark_card_http_404_raises():
    responses.add(responses.POST, WEBHOOK, status=404, body="")
    with pytest.raises(RuntimeError):
        send_lark_card(WEBHOOK, "secret", CARD)


# ---------------------------------------------------------------------------
# code != 0
# ---------------------------------------------------------------------------

@responses.activate
def test_send_lark_text_nonzero_code_raises_with_msg():
    responses.add(responses.POST, WEBHOOK, status=200,
                  json={"code": 19021, "msg": "sign check failed"})
    with pytest.raises(RuntimeError) as exc_info:
        send_lark_text(WEBHOOK, "secret", "hi")
    assert "19021" in str(exc_info.value)


@responses.activate
def test_send_lark_card_nonzero_code_raises():
    responses.add(responses.POST, WEBHOOK, status=200,
                  json={"code": 9499, "msg": "card rejected"})
    with pytest.raises(RuntimeError):
        send_lark_card(WEBHOOK, "secret", CARD)


# ---------------------------------------------------------------------------
# HTTP 200 但 body 不是合法 JSON
# ---------------------------------------------------------------------------

@responses.activate
def test_send_lark_text_non_json_body_raises():
    responses.add(responses.POST, WEBHOOK, status=200,
                  body="<html>upstream error</html>",
                  content_type="text/html")
    with pytest.raises(RuntimeError):
        send_lark_text(WEBHOOK, "secret", "hi")


# ---------------------------------------------------------------------------
# _post_json: code 字段缺失 / 顶层非 dict
# ---------------------------------------------------------------------------

@responses.activate
def test_post_json_missing_code_field_treated_as_failure():
    responses.add(responses.POST, WEBHOOK, status=200, json={"msg": "ok"})
    with pytest.raises(RuntimeError):
        _post_json(WEBHOOK, {"msg_type": "text"}, 5)


@responses.activate
def test_post_json_list_response_raises():
    responses.add(responses.POST, WEBHOOK, status=200, json=["not", "a", "dict"])
    with pytest.raises(RuntimeError, match="不是 dict"):
        _post_json(WEBHOOK, {"msg_type": "text"}, 5)


# ---------------------------------------------------------------------------
# 入参合法性
# ---------------------------------------------------------------------------

def test_send_lark_text_rejects_empty_text():
    with pytest.raises(ValueError):
        send_lark_text(WEBHOOK, "secret", "   ")


def test_send_lark_card_rejects_non_dict_card():
    with pytest.raises((ValueError, TypeError)):
        send_lark_card(WEBHOOK, "secret", "not a dict")  # type: ignore[arg-type]


def test_send_lark_card_rejects_empty_card():
    with pytest.raises(ValueError):
        send_lark_card(WEBHOOK, "secret", {})


def test_send_lark_text_rejects_invalid_webhook():
    with pytest.raises(ValueError):
        send_lark_text("file:///etc/passwd", "s", "hi")


def test_send_lark_text_rejects_empty_webhook():
    with pytest.raises(ValueError):
        send_lark_text("", "s", "hi")


# ---------------------------------------------------------------------------
# 频率限制重试（code=11232）
# ---------------------------------------------------------------------------

@responses.activate
def test_rate_limit_then_success():
    """第一次 11232、第二次 code=0 → 成功，且等待过 30 秒。"""
    responses.add(responses.POST, WEBHOOK, status=200,
                  json={"code": 11232, "msg": "frequency limited"})
    responses.add(responses.POST, WEBHOOK, status=200,
                  json={"code": 0, "msg": "ok"})

    sleeps = []
    with patch("lark.time.sleep", lambda s: sleeps.append(s)):
        data = _post_json(WEBHOOK, {"msg_type": "text", "content": {"text": "hi"}}, 5)

    assert data == {"code": 0, "msg": "ok"}
    assert sleeps == [30]
    assert len(responses.calls) == 2


@responses.activate
def test_rate_limit_exhausts_retries_raises():
    """连续 3 次 11232 → 抛 RuntimeError，sleep 2 次。"""
    for _ in range(3):
        responses.add(responses.POST, WEBHOOK, status=200,
                      json={"code": 11232, "msg": "frequency limited"})

    sleeps = []
    with patch("lark.time.sleep", lambda s: sleeps.append(s)):
        with pytest.raises(RuntimeError):
            _post_json(WEBHOOK, {"msg_type": "text", "content": {"text": "hi"}}, 5)

    assert sleeps == [30, 30]
    assert len(responses.calls) == 3


@responses.activate
def test_non_rate_limit_error_does_not_retry():
    """非 11232 错误码立刻抛错，不重试。"""
    responses.add(responses.POST, WEBHOOK, status=200,
                  json={"code": 9499, "msg": "card rejected"})

    sleeps = []
    with patch("lark.time.sleep", lambda s: sleeps.append(s)):
        with pytest.raises(RuntimeError) as exc_info:
            _post_json(WEBHOOK, {"msg_type": "text", "content": {"text": "hi"}}, 5)

    assert "9499" in str(exc_info.value)
    assert sleeps == []
    assert len(responses.calls) == 1
