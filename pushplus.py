"""PushPlus 微信推送通道。

通过 pushplus.plus API 将 markdown 消息推送到个人微信。
作为飞书推送的附加镜像通道，失败不影响主流程。
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_PUSHPLUS_URL = "https://www.pushplus.plus/send"
_TIMEOUT = (5, 15)
_UA = "Ainews-to-Feishu/1.0 (+https://github.com/Ai-luren/Ainews-to-Feishu)"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = _UA
    retry = Retry(total=2, backoff_factor=1.0,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["POST"]))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def send_pushplus(token: str, title: str, content: str) -> dict:
    """发送 markdown 消息到 PushPlus，返回响应 dict。

    token 为空时直接跳过（返回 {"code": 0, "msg": "skipped"}）。
    失败抛 RuntimeError。
    """
    if not token or not token.strip():
        return {"code": 0, "msg": "skipped: no token"}

    payload = {
        "token": token.strip(),
        "title": title or "AI 日报",
        "content": content,
        "template": "markdown",
    }
    with _session() as s:
        resp = s.post(_PUSHPLUS_URL, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, dict):
        raise RuntimeError(f"pushplus 响应非 dict: {type(data).__name__}")
    code = data.get("code", -1)
    if code != 200:
        msg = data.get("msg", "unknown")
        raise RuntimeError(f"pushplus 发送失败: code={code} msg={msg}")
    return data
