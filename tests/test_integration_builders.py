"""builders 端到端集成测试。

测试完整数据流：fetch_feed (mock) → get_top_tweets → _batch_translate (mock) → render_card → 验证卡片。
覆盖多 builder、排序、翻译、URL 安全校验等场景。
"""
from datetime import date
from unittest.mock import patch

import pytest
import responses

import builders
from builders import FEED_URL, _parse_date, fetch_daily, fetch_feed, has_content
from builders_card import render_card


def _make_feed(**overrides):
    """构造完整的 builders feed 响应体。"""
    base = {
        "generatedAt": "2026-07-01T00:30:00.000Z",
        "x": [
            {"name": "Sam Altman", "handle": "sama", "bio": "CEO of OpenAI",
             "tweets": [{"text": "GPT-5 is coming soon", "url": "https://x.com/sama/status/1", "likes": 5000, "retweets": 1000},
                        {"text": "AGI timeline thoughts", "url": "https://x.com/sama/status/2", "likes": 3000, "retweets": 800}]},
            {"name": "Yann LeCun", "handle": "ylecun", "bio": "Chief AI Scientist at Meta",
             "tweets": [{"text": "Open source AI is the future", "url": "https://x.com/ylecun/status/3", "likes": 8000, "retweets": 2000}]},
            {"name": "Andrej Karpathy", "handle": "karpathy", "bio": "Founder of Eureka Labs",
             "tweets": [{"text": "Teaching AI to code", "url": "https://x.com/karpathy/status/4", "likes": 6000, "retweets": 1500}]},
        ],
    }
    base.update(overrides)
    return base


@responses.activate
def test_integration_builders_full_pipeline():
    """完整数据流：feed mock → fetch_daily → render_card → 验证卡片。"""
    responses.add(responses.GET, FEED_URL, status=200, json=_make_feed())
    def mock_translate(text):
        return f"[译]{text}"
    with patch.object(builders, "_translate", mock_translate):
        daily = fetch_daily()
    assert daily is not None
    assert daily["date"] == date(2026, 7, 1)
    assert daily["total_builders"] == 3
    tweets = daily["tweets"]
    assert len(tweets) > 0
    engagements = [t["engagement"] for t in tweets]
    assert engagements == sorted(engagements, reverse=True)
    assert tweets[0]["engagement"] == 10000
    assert tweets[0]["handle"] == "ylecun"
    assert all("text_zh" in t for t in tweets)
    assert tweets[0]["text_zh"] == "[译]Open source AI is the future"
    assert all("bio_zh" in t for t in tweets)
    assert tweets[0]["bio_zh"] == "[译]Chief AI Scientist at Meta"
    card = render_card(daily)
    assert card is not None
    assert "config" in card
    assert "header" in card
    assert "elements" in card
    assert "2026-07-01" in card["header"]["title"]["content"]
    all_text = " ".join(e.get("text", {}).get("content", "") for e in card["elements"] if e.get("tag") == "div")
    assert "Open source AI" in all_text or "[译]Open source AI" in all_text
    assert "ylecun" in all_text
    actions = [e for e in card["elements"] if e.get("tag") == "action"]
    assert len(actions) == 1
    notes = [e for e in card["elements"] if e.get("tag") == "note"]
    assert len(notes) == 1


@responses.activate
def test_integration_builders_empty_feed():
    """空 feed → fetch_daily 返回 None。"""
    responses.add(responses.GET, FEED_URL, status=200, json={"generatedAt": "2026-07-01T00:30:00.000Z", "x": []})
    assert fetch_daily() is None


@responses.activate
def test_integration_builders_no_tweets():
    """有 builder 但无推文 → fetch_daily 返回 None。"""
    responses.add(responses.GET, FEED_URL, status=200,
        json={"generatedAt": "2026-07-01T00:30:00.000Z", "x": [{"name": "T", "handle": "t", "bio": "", "tweets": []}]})
    assert fetch_daily() is None


@responses.activate
def test_integration_builders_translate_failure_fallback():
    """翻译失败 → 走原文兜底。"""
    responses.add(responses.GET, FEED_URL, status=200, json=_make_feed())
    def failing_translate(text):
        raise RuntimeError("translate service down")
    with patch.object(builders, "_translate", failing_translate):
        daily = fetch_daily()
    assert daily is not None
    assert all(t["text_zh"] == t["text"] for t in daily["tweets"])
    card = render_card(daily)
    assert card is not None


@responses.activate
def test_integration_builders_partial_translate_failure():
    """部分翻译失败 → 失败的走原文。"""
    feed = _make_feed()
    feed["x"] = [{"name": "Test User", "handle": "testuser", "bio": "AI researcher",
        "tweets": [{"text": "should translate", "url": "u1", "likes": 100, "retweets": 10},
                   {"text": "should fail", "url": "u2", "likes": 50, "retweets": 5}]}]
    responses.add(responses.GET, FEED_URL, status=200, json=feed)
    def partial_translate(text):
        if "fail" in text:
            raise RuntimeError("translate error")
        return "[译]" + text
    with patch.object(builders, "_translate", partial_translate):
        daily = fetch_daily()
    assert daily is not None
    tweets = daily["tweets"]
    ok_tweet = next(t for t in tweets if "should translate" in t["text"])
    fail_tweet = next(t for t in tweets if "should fail" in t["text"])
    assert ok_tweet["text_zh"] == "[译]should translate"
    assert fail_tweet["text_zh"] == "should fail"


@responses.activate
def test_integration_builders_engagement_ordering():
    """互动量排序正确。"""
    feed = _make_feed()
    feed["x"][0]["tweets"][0]["likes"] = 100
    feed["x"][0]["tweets"][0]["retweets"] = 50
    feed["x"][1]["tweets"][0]["likes"] = 500
    feed["x"][1]["tweets"][0]["retweets"] = 200
    feed["x"][2]["tweets"][0]["likes"] = 300
    feed["x"][2]["tweets"][0]["retweets"] = 100
    responses.add(responses.GET, FEED_URL, status=200, json=feed)
    with patch.object(builders, "_translate", lambda t: f"[译]{t}"):
        daily = fetch_daily()
    assert daily is not None
    engagements = [t["engagement"] for t in daily["tweets"]]
    assert engagements == sorted(engagements, reverse=True)
    assert engagements[0] == 700


@responses.activate
def test_integration_builders_limit_truncation():
    """超过 MAX_TWEETS 被截断。"""
    builders_list = []
    for i in range(15):
        builders_list.append({"name": f"Builder {i}", "handle": f"builder_{i}", "bio": f"Bio {i}",
            "tweets": [{"text": f"tweet {i}", "url": f"https://x.com/b{i}/1", "likes": 100 - i, "retweets": 0}]})
    feed = {"generatedAt": "2026-07-01T00:30:00.000Z", "x": builders_list}
    responses.add(responses.GET, FEED_URL, status=200, json=feed)
    with patch.object(builders, "_translate", lambda t: t):
        daily = fetch_daily()
    assert daily is not None
    assert len(daily["tweets"]) == builders.MAX_TWEETS
    card = render_card(daily)
    assert card is not None


@responses.activate
def test_integration_builders_non_dict_response():
    """feed 返回非 dict → 抛 ValueError。"""
    responses.add(responses.GET, FEED_URL, status=200, json=[1, 2, 3])
    with pytest.raises(ValueError, match="非 dict"):
        fetch_feed()


@responses.activate
def test_integration_builders_card_has_action_url():
    """卡片 action 按钮指向正确 URL。"""
    responses.add(responses.GET, FEED_URL, status=200, json=_make_feed())
    with patch.object(builders, "_translate", lambda t: t):
        daily = fetch_daily()
    card = render_card(daily)
    assert card is not None
    actions = [e for e in card["elements"] if e.get("tag") == "action"]
    assert len(actions) == 1
    action_str = str(actions[0])
    assert "follow-builders" in action_str or "github.com" in action_str
