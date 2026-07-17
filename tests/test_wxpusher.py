"""WxPusher 极简推送（SPT）通道测试。"""
import pytest
import responses

from wxpusher import _WXPUSHER_URL, send_wxpusher


# ---------------------------------------------------------------------------
# spt 为空 → 跳过
# ---------------------------------------------------------------------------

def test_send_wxpusher_empty_spt_skips():
    """spt 为空时直接跳过，不发请求。"""
    result = send_wxpusher("", "title", "content")
    assert result["code"] == 0
    assert "skipped" in result["msg"]


def test_send_wxpusher_whitespace_spt_skips():
    """spt 只有空白字符时也跳过。"""
    result = send_wxpusher("   ", "title", "content")
    assert result["code"] == 0


# ---------------------------------------------------------------------------
# 正常发送
# ---------------------------------------------------------------------------

@responses.activate
def test_send_wxpusher_success():
    """code=1000 → 发送成功，返回响应 dict。"""
    responses.add(responses.POST, _WXPUSHER_URL, status=200,
                  json={"code": 1000, "msg": "处理成功", "data": [], "success": True})
    result = send_wxpusher("SPT_test123", "标题", "## 内容")
    assert result["code"] == 1000
    assert result["success"] is True

    body = responses.calls[0].request.body.decode()
    assert '"spt": "SPT_test123"' in body
    assert '"contentType": 3' in body
    assert "## " in body  # content 包含 markdown 标题


@responses.activate
def test_send_wxpusher_default_title_when_empty():
    """title 为空时 summary 使用默认标题。"""
    responses.add(responses.POST, _WXPUSHER_URL, status=200,
                  json={"code": 1000, "msg": "ok", "data": [], "success": True})
    send_wxpusher("SPT_tok", "", "content")
    body = responses.calls[0].request.body.decode()
    assert "AI" in body  # 默认标题含 "AI 日报"（中文被 unicode 编码）
    assert '"summary"' in body


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------

@responses.activate
def test_send_wxpusher_non_1000_code_raises():
    """code != 1000 → RuntimeError。"""
    responses.add(responses.POST, _WXPUSHER_URL, status=200,
                  json={"code": 1003, "msg": "spt无效"})
    with pytest.raises(RuntimeError, match="1003"):
        send_wxpusher("bad_spt", "title", "content")


@responses.activate
def test_send_wxpusher_http_error_raises():
    """HTTP 500 → raise_for_status 抛错。"""
    responses.add(responses.POST, _WXPUSHER_URL, status=500, body="server error")
    with pytest.raises(Exception):
        send_wxpusher("SPT_tok", "title", "content")


@responses.activate
def test_send_wxpusher_non_dict_response_raises():
    """响应非 dict → RuntimeError。"""
    responses.add(responses.POST, _WXPUSHER_URL, status=200, json=["not", "dict"])
    with pytest.raises(RuntimeError, match="非 dict"):
        send_wxpusher("SPT_tok", "title", "content")


@responses.activate
def test_send_wxpusher_missing_code_field_raises():
    """响应缺 code 字段 → RuntimeError（默认 -1 != 1000）。"""
    responses.add(responses.POST, _WXPUSHER_URL, status=200, json={"msg": "ok"})
    with pytest.raises(RuntimeError, match="-1"):
        send_wxpusher("SPT_tok", "title", "content")
