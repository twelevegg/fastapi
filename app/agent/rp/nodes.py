from typing import Literal
import json
from app.agent.rp.memory_mapper import map_cause
from langchain_core.messages import BaseMessage

# 상태 전이 로직
from app.agent.rp.understanding import (
    update_understanding_level,
    update_current_goal,
    update_ready_to_close,
)

# OpenAI 호출
from app.services.openai_service import openai_service

# 프롬프트
from app.agent.rp.prompts import build_customer_system_prompt

# State 타입
from app.agent.rp.state import RPState as State

def normalize_messages(messages):
    normalized = []

    for m in messages:
        # 1️⃣ LangChain Message 객체
        if isinstance(m, BaseMessage):
            role = "user" if m.type == "human" else "assistant"
            normalized.append({
                "role": role,
                "content": m.content
            })
            continue

        # 2️⃣ dict 형태
        if isinstance(m, dict):
            # role / content 둘 다 있어야 통과
            if "role" in m and "content" in m:
                normalized.append({
                    "role": m["role"],
                    "content": m["content"]
                })
                continue
            else:
                raise ValueError(f"Invalid message dict (missing role/content): {m}")

        # 3️⃣ 그 외 타입은 전부 에러
        raise ValueError(f"Unsupported message type: {type(m)} → {m}")

    return normalized

def init_state_node(state: State):
    return {
        "messages": state.get("messages", []),
        "current_goal": "요금이 왜 이렇게 많이 나왔는지 이유를 알고 싶다",
        "understanding_level": 0,
        "ready_to_close": False,
        "qa_result": None,
        "memory": {},
        "memory_candidate": None,
    }



# ===============================
# 공통: LLM 메시지 빌더
# ===============================
def build_llm_messages(state: State, max_turns: int = 6):
    """
    LLM에게 전달할 컨텍스트 구성
    - 요약이 있으면 system으로 제공
    - 캐릭터 system prompt 1회만 주입
    - 최근 N턴만 컨텍스트로 사용
    """
    messages = []

    messages.append(build_customer_system_prompt(state))
    messages.extend(state["messages"][-max_turns:])

    return messages


# ===============================
# 상태 업데이트 노드
# ===============================
def state_update_node(state: State):
    if not state["messages"]:
        return state

    last_msg = state["messages"][-1]

    # HumanMessage / AIMessage 공통
    last_content = last_msg.content

    update_understanding_level(state, last_content)
    update_current_goal(state)
    update_ready_to_close(state)

    return state


# ===============================
# 일반 대화 노드
# ===============================
async def customer_talk_node(state: State):
    messages = build_llm_messages(state)
    messages = normalize_messages(messages)

    text = await openai_service.rpchat(
        messages=messages,
        model="gpt-4o-mini",
        max_tokens=120,
    )

    return {
        "messages": [{
            "role": "assistant",
            "content": text
        }]
    }


# ===============================
# 종료 대화 노드
# ===============================
async def close_talk_node(state: State):
    messages = build_llm_messages(state)
    messages = normalize_messages(messages)

    text = await openai_service.rpchat(
        messages=messages,
        model="gpt-4o-mini",
        max_tokens=80,
    )

    return {
        "messages": [{
            "role": "assistant",
            "content": text
        }]
    }


# ===============================
# QA 평가 노드
# ===============================
async def qa_evaluate_node(state: State):
    convo = ""
    for m in state.get("messages", []):
        role = "상담사" if m.type == "human" else "고객"
        convo += f"{role}: {m.content}\n"

    qa_prompt = f"""
당신은 통신사 고객센터의 내부 품질관리(QA) 평가자입니다.
아래 상담 내용을 객관적인 기준에 따라 평가하십시오.

⚠️ 감정적 판단이나 추측은 하지 말고,
상담사가 실제로 수행한 발언과 흐름만을 근거로 평가합니다.

────────────────
[평가 기준 및 판단 가이드]

1. 문제 파악 정확성
- 고객의 핵심 불만(요금, 해지, 불만 사유 등)을 초반에 정확히 파악했는가
- 불필요한 질문 없이 요점을 짚었는가

2. 요금 설명 명확성
- 요금/정책/조건 설명이 구체적이고 이해하기 쉬운가
- 모호한 표현이나 책임 회피성 설명은 없었는가

3. 응대 태도
- 고객의 감정에 공감하는 표현이 있었는가
- 방어적, 무성의, 기계적인 응대는 없었는가

4. 상담 흐름 적절성
- 상담이 논리적인 순서(문제 확인 → 설명 → 해결/안내)로 진행되었는가
- 동일한 설명을 불필요하게 반복하지 않았는가

5. 상담 종료의 자연스러움
- 고객이 납득할 수 있는 마무리 멘트가 있었는가
- 일방적인 종료나 미완의 종료는 아니었는가

────────────────
[점수 기준]

- 5점: 매우 우수 (모든 항목이 명확하고 안정적)
- 4점: 전반적으로 우수하나 사소한 아쉬움 있음
- 3점: 기본은 충족하나 개선 필요 요소 다수
- 2점: 미흡, 고객 불만 가능성 있음
- 1점: 부적절, QA 기준 미달

────────────────
[출력 형식 - 반드시 JSON만 출력]

{{
  "overall_score": 1~5,
  "strengths": ["상담에서 잘 수행된 점을 구체적으로 서술"],
  "weaknesses": ["개선이 필요한 부분을 행동 기준으로 서술"],
  "one_line_feedback": "QA 관점에서의 핵심 피드백 한 문장"
}}

⚠️ JSON 외의 설명 문장은 절대 출력하지 마십시오.

[상담 내용]
{convo}
"""

    text = await openai_service.rpchat(
        messages=[{"role": "system", "content": qa_prompt}],
        model="gpt-4o-mini",
        max_tokens=300,
    )

    try:
        state["qa_result"] = json.loads(text)  # ✅ 핵심
    except json.JSONDecodeError:
        # fallback (혹시 LLM이 JSON 깨면)
        state["qa_result"] = {
            "raw_text": text
        }
    return state

# ===============================
# MEMORY 노드
# ===============================

async def memory_extraction_node(state: State):
    last_msg = state["messages"][-1]
    prompt = f"""
다음 대화에서
요금 증가의 원인을 사실 기반으로만 추출하세요.

- 추측 금지
- 명시된 원인만
- JSON 배열로 출력

[상담사 설명]
{last_msg.content}

[출력 예]
[
  {{ "cause_text": "데이터 사용량 초과" }}
]
"""

    text = await openai_service.rpchat(
        messages=[{"role": "system", "content": prompt}],
        model="gpt-4o-mini",
        max_tokens=200,
    )

    return {
        "memory_candidate": {
            "explained_causes": json.loads(text)
        }
    }

def memory_apply_node(state: State):
    candidate = state.get("memory_candidate")
    if not candidate:
        return state

    memory = state.get("memory", {}) or {}

    explained = []
    for item in candidate.get("explained_causes", []):
        mapped = map_cause(item["cause_text"])
        if mapped:
            explained.append(mapped)

    if explained:
        prev = memory.get("explained_causes", [])
        memory["explained_causes"] = prev + explained


    state["memory"] = memory
    state["memory_candidate"] = None

    return state

# ===============================
# 분기 조건
# ===============================
def decide_mode(state: State) -> Literal["talk", "close"]:
    return "close" if state["ready_to_close"] else "talk"
