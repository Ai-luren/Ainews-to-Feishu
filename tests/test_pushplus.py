"""pushplus 微信推送通道测试。"""
import pytest
import responses

from pushplus import _PUSHPLUS_URL, send_pushplus


# ---------------------------------------------------------------------------
# token 为空 → 跳过
# ---------------------------------------------------------------------------

def test_send_pushplus_empty_token_skips():
    """token 为空时直接跳过，不发请求。"""
    result = send_pushplus("", "title", "content")
    assert result["code"] == 0
    assert "skipped" in result["msg"]


def test_send_pushplus_whitespace_token_skips():
    """token 只有空白字符时也跳过。"""
    result = send_pushplus("   ", "title", "content")
    assert result["code"] == 0


# ---------------------------------------------------------------------------
# 正常发送
# ---------------------------------------------------------------------------

@responses.activate
def test_send_pushplus_success():
    """code=200 → 发送成功，返回响应 dict。"""
    responses.add(responses.POST, _PUSHPLUS_URL, status=200,
                  json={"code": 200, "msg": "请求成功", "data": "abc123"})
    result = send_pushplus("tok123", "标题", "## 内容")
    assert result["code"] == 200
    assert result["data"] == "abc123"

    body = responses.calls[0].request.body.decode()
    assert '"token": "tok123"' in body
    assert '"template": "markdown"' in body
    assert "## " in body  # content 包含 markdown 标题


@responses.activate
def test_send_pushplus_default_title_when_empty():
    """title 为空时使用默认标题。"""
    responses.add(responses.POST, _PUSHPLUS_URL, status=200,
                  json={"code": 200, "msg": "ok", "data": "x"})
    send_pushplus("tok", "", "content")
    body = responses.calls[0].request.body.decode()
    assert "AI" in body  # 默认标题含 "AI 日报"（中文被 unicode 编码）


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------

@responses.activate
def test_send_pushplus_non_200_code_raises():
    """code != 200 → RuntimeError。"""
    responses.add(responses.POST, _PUSHPLUS_URL, status=200,
                  json={"code": 900, "msg": "token无效"})
    with pytest.raises(RuntimeError, match="900"):
        send_pushplus("bad_token", "title", "content")


@responses.activate
def test_send_pushplus_http_error_raises():
    """HTTP 500 → raise_for_status 抛错。"""
    responses.add(responses.POST, _PUSHPLUS_URL, status=500, body="server error")
    with pytest.raises(Exception):
        send_pushplus("tok", "title", "content")


@responses.activate
def test_send_pushplus_non_dict_response_raises():
    """响应非 dict → RuntimeError。"""
    responses.add(responses.POST, _PUSHPLUS_URL, status=200, json=["not", "dict"])
    with pytest.raises(RuntimeError, match="非 dict"):
        send_pushplus("tok", "title", "content")


@responses.activate
def test_send_pushplus_missing_code_field_raises():
    """响应缺 code 字段 → RuntimeError（默认 -1 != 200）。"""
    responses.add(responses.POST, _PUSHPLUS_URL, status=200, json={"msg": "ok"})
    with pytest.raises(RuntimeError, match="-1"):
        send_pushplus("tok", "title", "content")
