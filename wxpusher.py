"""WxPusher 微信推送通道（极简推送 SPT 模式）。

通过 WxPusher API 将 markdown 消息推送到个人微信。
使用极简推送（SPT）模式，只需一个 SPT token，无需注册创建应用。
作为飞书推送的附加镜像通道，失败不影响主流程。

获取 SPT：扫码 https://wxpusher.zjiecode.com/api/qrcode/RwjGLMOPTYp35zSYQr0HxbCPrV9eU0wKVBXU1D5VVtya0cQXEJWPjqBdW3gKLifS.jpg
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 极简推送接口（与标准推送 /api/send/message 不同）
_WXPUSHER_URL = "https://wxpusher.zjiecode.com/api/send/message/simple-push"
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


def send_wxpusher(spt: str, title: str, content: str) -> dict:
    """发送 markdown 消息到 WxPusher，返回响应 dict。

    spt 为空时直接跳过（返回 {"code": 0, "msg": "skipped"}）。
    失败抛 RuntimeError。
    """
    if not spt or not spt.strip():
        return {"code": 0, "msg": "skipped: no spt"}

    payload = {
        "spt": spt.strip(),
        "content": content,
        "summary": title or "AI 日报",
        "contentType": 3,  # 3=markdown
    }
    with _session() as s:
        resp = s.post(_WXPUSHER_URL, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, dict):
        raise RuntimeError(f"wxpusher 响应非 dict: {type(data).__name__}")
    code = data.get("code", -1)
    if code != 1000:  # WxPusher 成功码是 1000
        msg = data.get("msg", "unknown")
        raise RuntimeError(f"wxpusher 发送失败: code={code} msg={msg}")
    return data
