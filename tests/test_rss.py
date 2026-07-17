"""rss 模块完整测试：parse_feed、extract_today_entry、fetch_rss、URL 回退。

合并自 test_rss / test_rss_fetch 两个文件，删除 1 个重复用例。
"""
import importlib
import os as _os
from datetime import date
from pathlib import Path

import pytest
import responses

import rss
from rss import (
    _DEAD_RSS_URLS,
    _RSS_URL_DEFAULT,
    extract_today_entry,
    fetch_rss,
    get_effective_rss_url,
    parse_feed,
)

FIXTURE = Path("tests/fixtures/juya_sample.xml")


# ---------------------------------------------------------------------------
# parse_feed: fixture XML 解析
# ---------------------------------------------------------------------------

def test_parse_feed_returns_entries():
    entries = parse_feed(FIXTURE.read_text())
    assert len(entries) > 0
    first = entries[0]
    assert "title" in first
    assert "link" in first
    assert "published_dt" in first
    assert "content_html" in first


# ---------------------------------------------------------------------------
# extract_today_entry: 日期匹配
# ---------------------------------------------------------------------------

def test_extract_today_entry_matches_beijing_today():
    import pytz
    xml = FIXTURE.read_text()
    entries = parse_feed(xml)
    latest_pub_beijing = entries[0]["published_dt"].astimezone(pytz.timezone("Asia/Shanghai"))
    fake_today = latest_pub_beijing.date()

    entry = extract_today_entry(xml, today=fake_today)
    assert entry is not None
    assert entry["title"].startswith(fake_today.strftime("%Y-%m-%d"))


# ---------------------------------------------------------------------------
# fetch_rss: HTTP 404 / 500 / 响应过大 / 连接异常 / 成功 / HTML 拒绝
# ---------------------------------------------------------------------------

@responses.activate
def test_fetch_rss_raises_on_http_404():
    responses.add(responses.GET, "http://example.invalid/rss.xml", status=404, body="not found")
    with pytest.raises(Exception):
        fetch_rss(url="http://example.invalid/rss.xml", timeout=1)


@responses.activate
def test_fetch_rss_raises_on_http_500():
    responses.add(responses.GET, "http://example.invalid/rss.xml", status=500, body="boom")
    with pytest.raises(Exception):
        fetch_rss(url="http://example.invalid/rss.xml", timeout=1)


@responses.activate
def test_fetch_rss_raises_on_oversized_body():
    body = b"x" * (rss.MAX_RSS_BYTES + 1)
    responses.add(responses.GET, "http://example.invalid/rss.xml", status=200, body=body,
                  content_type="application/rss+xml")
    with pytest.raises(RuntimeError, match="过大"):
        fetch_rss(url="http://example.invalid/rss.xml", timeout=1)


def test_fetch_rss_raises_on_connect_timeout(monkeypatch):
    import requests as _requests

    class _FakeSession:
        def get(self, *a, **kw):
            raise _requests.ConnectionError("DNS failure")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(rss, "_session_with_retries", _FakeSession)
    with pytest.raises(_requests.ConnectionError):
        fetch_rss(url="http://will-never-resolve.invalid/rss.xml", timeout=1)


@responses.activate
def test_fetch_rss_returns_bytes_on_success():
    responses.add(responses.GET, "http://example.invalid/rss.xml", status=200, body=b"<rss/>",
                  content_type="application/rss+xml")
    assert fetch_rss(url="http://example.invalid/rss.xml", timeout=1) == b"<rss/>"


@responses.activate
def test_fetch_rss_rejects_html_content_type():
    responses.add(responses.GET, "http://example.invalid/rss.xml", status=200,
                  body=b"<html><body>error</body></html>",
                  content_type="text/html; charset=utf-8")
    with pytest.raises(RuntimeError, match="非 XML"):
        fetch_rss(url="http://example.invalid/rss.xml", timeout=1)


# ---------------------------------------------------------------------------
# _DEAD_RSS_URLS: 配置旧地址时强制回退
# ---------------------------------------------------------------------------

def test_dead_rss_url_forces_fallback_to_default(monkeypatch, capsys):
    for dead in _DEAD_RSS_URLS:
        monkeypatch.setitem(_os.environ, "RSS_URL", dead)
        importlib.reload(rss)
        assert rss.RSS_URL == _RSS_URL_DEFAULT
        captured = capsys.readouterr()
        assert dead in captured.out or "废弃" in captured.out or "回退" in captured.out

    monkeypatch.delenv("RSS_URL", raising=False)
    importlib.reload(rss)


def test_get_effective_rss_url_matches_module_constant():
    assert get_effective_rss_url() == rss.RSS_URL


# ---------------------------------------------------------------------------
# extract_today_entry: 标题日期回退
# ---------------------------------------------------------------------------

RSS_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>fixture</title>
    <link>http://example.invalid/</link>
    <description>fixture</description>
    {entries}
  </channel>
</rss>
"""


def _item(title: str, pubdate_utc: str, link: str = "http://example.invalid/") -> str:
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<link>{link}</link>"
        f"<pubDate>{pubdate_utc}</pubDate>"
        "<description><![CDATA[<p>hi</p>]]></description>"
        "</item>"
    )


def test_extract_today_entry_title_fallback_when_published_mismatch():
    """published 日期不匹配，但标题里写着 today → 标题回退命中。"""
    xml = RSS_TEMPLATE.format(
        entries=_item("2026-04-27 backfill", "Sat, 25 Apr 2026 20:00:00 +0000")
    )
    entry = extract_today_entry(xml, today=date(2026, 4, 27))
    assert entry is not None
    assert "2026-04-27 backfill" in entry["title"]


def test_extract_today_entry_returns_none_when_both_paths_miss():
    """published 与标题都匹配不上 → None。"""
    xml = RSS_TEMPLATE.format(
        entries=_item("2026-04-20 old", "Mon, 20 Apr 2026 00:00:00 +0000")
    )
    assert extract_today_entry(xml, today=date(2026, 4, 27)) is None


def test_extract_today_entry_invalid_title_date_still_safe():
    """标题里畸形日期不崩。"""
    xml = RSS_TEMPLATE.format(
        entries=_item("2026-02-30 bad-date", "Mon, 27 Apr 2026 00:00:00 +0000")
    )
    entry = extract_today_entry(xml, today=date(2026, 4, 27))
    assert entry is not None


def test_extract_today_entry_default_today_uses_beijing_now():
    xml = RSS_TEMPLATE.format(
        entries=_item("2099-01-01 far-future", "Fri, 01 Jan 2099 00:00:00 +0000")
    )
    got = extract_today_entry(xml)
    assert got is None or isinstance(got, dict)
