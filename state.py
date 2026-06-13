import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional


def load_state(path: Path) -> Dict[str, Any]:
    """加载 state.json。空文件 / 格式错误 / 非 dict / 文件不存在时回退到空 dict。"""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = ""
    except OSError as e:
        print(f"[warn] state.json 读失败：{e}", flush=True)
        raw = ""
    if not raw.strip():
        data: Dict[str, Any] = {}
    else:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                print(f"[warn] state.json 顶层不是 dict（是 {type(data).__name__}），重置", flush=True)
                data = {}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[warn] state.json 解析失败：{e}", flush=True)
            data = {}
    data.setdefault("last_pushed_date", None)
    data.setdefault("consecutive_failures", 0)
    data.setdefault("last_juya_entry_date", None)
    data.setdefault("juya_dead_alerted_on", None)
    return data


def save_state(path: Path, data: Dict[str, Any]) -> None:
    """原子写入：先写临时文件，再用 os.replace 交换，保证不会半截写入。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def is_pushed_today(path: Path, today: date) -> bool:
    data = load_state(path)
    return data.get("last_pushed_date") == today.isoformat()


def mark_pushed_today(path: Path, today: date) -> None:
    data = load_state(path)
    data["last_pushed_date"] = today.isoformat()
    data["consecutive_failures"] = 0
    save_state(path, data)


def bump_failure(path: Path) -> int:
    data = load_state(path)
    try:
        n = int(data.get("consecutive_failures", 0)) + 1
    except (TypeError, ValueError):
        n = 1
    data["consecutive_failures"] = n
    save_state(path, data)
    return n


def reset_failure(path: Path) -> None:
    data = load_state(path)
    data["consecutive_failures"] = 0
    save_state(path, data)


def record_juya_entry_date(path: Path, entry_date: date) -> None:
    data = load_state(path)
    data["last_juya_entry_date"] = entry_date.isoformat()
    data["juya_dead_alerted_on"] = None
    save_state(path, data)


def get_last_juya_entry_date(path: Path) -> Optional[date]:
    data = load_state(path)
    last = data.get("last_juya_entry_date")
    if not last:
        return None
    try:
        return date.fromisoformat(last)
    except ValueError:
        return None


def juya_silent_days(path: Path, today: date) -> Optional[int]:
    last_d = get_last_juya_entry_date(path)
    if last_d is None:
        return None
    return max((today - last_d).days, 0)


def should_alert_juya_dead(path: Path, today: date) -> bool:
    data = load_state(path)
    return data.get("juya_dead_alerted_on") != today.isoformat()


def mark_juya_dead_alerted(path: Path, today: date) -> None:
    data = load_state(path)
    data["juya_dead_alerted_on"] = today.isoformat()
    save_state(path, data)
