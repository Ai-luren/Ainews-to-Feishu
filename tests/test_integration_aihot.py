"""aihot 端到端集成测试。

测试完整数据流：fetch_daily (API mock) → parse_daily_to_card → 验证卡片结构。
覆盖多 section、导语、快讯、URL 安全校验等场景。
"""
from datetime import date
from unittest.mock import patch

import pytest
import responses

import aihot
from aihot import AIHOT_BASE_URL, fetch_daily, has_content, total_items
from aihot_card import parse_daily_to_card


def _make_report(**overrides):
    """构造完整的 aihot v1 API 响应。"""
    base = {
        "date": "2026-06-24",
        "sections": [
            {
                "label": "大模型",
                "items": [
                    {
                        "title": "OpenAI 发布 GPT-5",
                        "links": {"original": "https://example.com/gpt5"},
                        "summary": "GPT-5 在推理能力上大幅提升",
                        "source": {"name": "OpenAI Blog"},
                    },
                    {
                        "title": "Anthropic 推出 Claude 4",
                        "links": {"original": "https://example.com/claude4"},
                        "summary": "Claude 4 支持百万 token 上下文",
                        "source": {"name": "Anthropic"},
                    },
                ],
            },
            {
                "label": "开源动态",
                "items": [
                    {
                        "title": "Llama 4 开源发布",
                        "links": {"original": "https://example.com/llama4"},
                        "summary": "Meta 发布最新开源大模型",
                        "source": {"name": "Meta AI"},
                    },
                ],
            },
        ],
        "flashes": [
            {
                "title": "Google I/O 2026 开幕",
                "links": {"original": "https://example.com/google-io"},
            },
        ],
        "lead": {
            "title": "今日导语",
            "leadParagraph": "AI 领域今天有多项重大发布。",
        },
    }
    base.update(overrides)
    return {"report": base}


@responses.activate
def test_integration_aihot_full_pipeline():
    """完整数据流：API mock → fetch_daily → parse_daily_to_card → 验证卡片。"""
    responses.add(
        responses.GET,
        f"{AIHOT_BASE_URL}/api/v1/dailies/latest",
        status=200,
        json=_make_report(),
    )
    daily = fetch_daily()
    assert daily is not None
    assert daily["date"] == "2026-06-24"
    assert has_content(daily)
    assert total_items(daily) == 3
    card = parse_daily_to_card(daily)
    assert card is not None
    assert card["config"]["wide_screen_mode"] is True
    assert isinstance(card["elements"], list)
    assert len(card["elements"]) >= 1
    assert "2026-06-24" in card["header"]["title"]["content"]
    all_text = " ".join(
        e.get("text", {}).get("content", "")
        for e in card["elements"]
        if e.get("tag") == "div"
    )
    assert "大模型" in all_text
    assert "开源动态" in all_text
    assert "GPT-5" in all_text
    assert "Claude 4" in all_text
    assert "Llama 4" in all_text
    assert "今日导语" in all_text
    assert "Google I/O" in all_text
    actions = [e for e in card["elements"] if e.get("tag") == "action"]
    assert len(actions) == 1
    notes = [e for e in card["elements"] if e.get("tag") == "note"]
    assert len(notes) == 1


@responses.activate
def test_integration_aihot_target_date():
    """指定日期拉取。"""
    target = date(2026, 6, 24)
    responses.add(
        responses.GET,
        f"{AIHOT_BASE_URL}/api/v1/dailies/{target}",
        status=200,
        json=_make_report(date="2026-06-24"),
    )
    daily = fetch_daily(target)
    assert daily is not None
    assert daily["date"] == "2026-06-24"
    card = parse_daily_to_card(daily)
    assert card is not None
    assert "2026-06-24" in card["header"]["title"]["content"]


@responses.activate
def test_integration_aihot_404_no_target():
    """无 target_date 时 404 → 抛异常。"""
    responses.add(responses.GET, f"{AIHOT_BASE_URL}/api/v1/dailies/latest", status=404)
    with pytest.raises(RuntimeError, match="404"):
        fetch_daily()


@responses.activate
def test_integration_aihot_404_with_target():
    """有 target_date 时 404 → 返回 None。"""
    target = date(2026, 6, 25)
    responses.add(responses.GET, f"{AIHOT_BASE_URL}/api/v1/dailies/{target}", status=404)
    assert fetch_daily(target) is None


@responses.activate
def test_integration_aihot_empty_sections():
    """空 sections → parse_daily_to_card 返回 None。"""
    responses.add(
        responses.GET, f"{AIHOT_BASE_URL}/api/v1/dailies/latest", status=200,
        json={"report": {"date": "2026-06-24", "sections": [], "flashes": [], "lead": None}},
    )
    daily = fetch_daily()
    assert daily is not None
    assert not has_content(daily)
    assert parse_daily_to_card(daily) is None


@responses.activate
def test_integration_aihot_javascript_url_sanitized():
    """javascript: URL 被替换为 #。"""
    responses.add(
        responses.GET, f"{AIHOT_BASE_URL}/api/v1/dailies/latest", status=200,
        json=_make_report(sections=[{"label": "测试", "items": [
            {"title": "恶意链接", "links": {"original": "javascript:alert(1)"},
             "summary": "xss", "source": {"name": "T"}}]}], flashes=[], lead=None),
    )
    daily = fetch_daily()
    card = parse_daily_to_card(daily)
    assert card is not None
    all_text = " ".join(e.get("text", {}).get("content", "") for e in card["elements"] if e.get("tag") == "div")
    assert "javascript:" not in all_text


@responses.activate
def test_integration_aihot_markdown_injection_escaped():
    """markdown 特殊字符被转义。"""
    responses.add(
        responses.GET, f"{AIHOT_BASE_URL}/api/v1/dailies/latest", status=200,
        json=_make_report(sections=[{"label": "测试", "items": [
            {"title": "Evil [click](http://evil.com)", "links": {"original": "https://safe.com"},
             "summary": "md inject", "source": {"name": "T"}}]}], flashes=[], lead=None),
    )
    daily = fetch_daily()
    card = parse_daily_to_card(daily)
    assert card is not None
    all_text = " ".join(e.get("text", {}).get("content", "") for e in card["elements"] if e.get("tag") == "div")
    assert "\\[click\\]" in all_text


@responses.activate
def test_integration_aihot_large_content_not_truncated():
    """多 section + 多条目不丢失内容。"""
    sections = []
    for i in range(5):
        sections.append({"label": f"分类{i}", "items": [
            {"title": f"标题-{i}-{j}", "links": {"original": f"https://example.com/{i}/{j}"},
             "summary": f"摘要-{i}-{j}", "source": {"name": f"来源{i}"}}
            for j in range(3)]})
    responses.add(
        responses.GET, f"{AIHOT_BASE_URL}/api/v1/dailies/latest", status=200,
        json=_make_report(sections=sections, flashes=[], lead=None),
    )
    daily = fetch_daily()
    assert total_items(daily) == 15
    card = parse_daily_to_card(daily)
    assert card is not None
    all_text = " ".join(e.get("text", {}).get("content", "") for e in card["elements"] if e.get("tag") == "div")
    for i in range(5):
        assert f"分类{i}" in all_text
        assert f"标题-{i}-0" in all_text
