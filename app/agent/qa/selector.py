from __future__ import annotations

import re
from typing import Optional

from .utils import unique_keep_order


KEYWORD_PATTERNS = [
    r"안녕하세요", r"상담사", r"무엇을\s*도와", r"본인\s*확인",  # 오프닝/확인
    r"요금", r"청구", r"과금", r"결제", r"소액결제", r"휴대폰\s*결제",
    r"데이터", r"초과", r"추가\s*요금", r"부가\s*서비스", r"콘텐츠",
    r"해지", r"환불", r"정지", r"납부", r"미납", r"연체",
    r"명의", r"가족", r"결합", r"약정",
    r"요약", r"정리", r"확인해\s*보", r"확인\s*드리", r"마무리", r"도와드릴",
]
KEYWORD_RE = re.compile("|".join(KEYWORD_PATTERNS))


def pick_representative_agent_turns(
    messages: list[dict[str, str]],
    max_turn_evals: int = 10,
    use_keyword_pick: bool = True,
    keyword_re: Optional[re.Pattern] = None,
) -> list[int]:
    """
    - 상담사 발화(role=user) 인덱스만 후보
    - 오프닝(첫 상담사 발화) 무조건 포함
    - 마무리(마지막 상담사 발화) 무조건 포함
    - (옵션) 키워드 매칭되는 상담사 발화 포함
    - 남는 자리는 전체 범위를 고르게 커버(균등 샘플)
    - max_turn_evals=0이면 상담사 발화 전체 평가
    """
    agent_turns = [i for i, m in enumerate(messages) if m["role"] == "user"]
    if not agent_turns:
        return []

    if max_turn_evals == 0 or len(agent_turns) <= max_turn_evals:
        return agent_turns

    opening = agent_turns[0]
    closing = agent_turns[-1]

    selected = [opening, closing]

    pat = keyword_re or KEYWORD_RE
    if use_keyword_pick:
        for idx in agent_turns[1:-1]:
            if pat.search(messages[idx]["content"]):
                selected.append(idx)

    selected = unique_keep_order(selected)

    # 균등 샘플로 전체 커버
    cap = max_turn_evals
    if len(selected) < cap:
        remaining = [x for x in agent_turns if x not in set(selected)]
        need = cap - len(selected)
        if remaining and need > 0:
            step = max(1, len(remaining) // need)
            sampled = remaining[::step][:need]
            selected.extend(sampled)

    selected = unique_keep_order(selected)

    # cap 초과 시 균등 축소 (opening/closing 유지)
    if len(selected) > cap:
        must = unique_keep_order([opening, closing])
        rest = [x for x in selected if x not in set(must)]
        keep = cap - len(must)
        if keep <= 0:
            return must[:cap]
        step = max(1, len(rest) // keep)
        rest_kept = rest[::step][:keep]
        selected = unique_keep_order(must + rest_kept)

    return selected[:cap]
