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
            normalized.append({"role": role, "content": m.content})
            continue

        # 2️⃣ dict 형태
        if isinstance(m, dict):
            # role / content 둘 다 있어야 통과
            if "role" in m and "content" in m:
                normalized.append({"role": m["role"], "content": m["content"]})
                continue
            else:
                raise ValueError(f"Invalid message dict (missing role/content): {m}")

        # 3️⃣ 그 외 타입은 전부 에러
        raise ValueError(f"Unsupported message type: {type(m)} → {m}")

    return normalized


def init_state_node(state: State):
    persona = state.get("persona")
    start_call = state.get("start_call")
    return {
        "messages": state.get("messages", []),
        "current_goal": "요금이 왜 이렇게 많이 나왔는지 이유를 알고 싶다",
        "understanding_level": 0,
        "ready_to_close": False,
        "persona": persona,
        "start_call": start_call,
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
        "messages": [{"role": "assistant", "content": text}],
        "start_call": False,
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
        "messages": [{"role": "assistant", "content": text}],
        "start_call": False,
    }


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

    # Markdown json block cleanup
    cleaned_text = text.replace("```json", "").replace("```", "").strip()

    try:
        parsed_json = json.loads(cleaned_text)
    except json.JSONDecodeError:
        print(f"JSON Parse Error. Raw text: {text}")
        parsed_json = []

    return {"memory_candidate": {"explained_causes": parsed_json}}


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
