from __future__ import annotations

import json
from typing import Any, Iterable


def safe_json_loads(text: str) -> dict[str, Any]:
    """LLM이 JSON 앞/뒤로 잡텍스트를 붙여도 최대한 파싱."""
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def build_convo_text(messages: list[dict[str, str]]) -> str:
    lines = []
    for m in messages:
        role = "상담사" if m["role"] == "user" else "고객"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)


def unique_keep_order(items: Iterable[int]) -> list[int]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
