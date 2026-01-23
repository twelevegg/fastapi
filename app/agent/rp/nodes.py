from typing import Literal

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


def init_state_node(state: State):
    """
    LangGraph 최초 진입 시 state 기본값 보장
    """
    return {
        "messages": state.get("messages", []),
        "summary": None,
        "current_goal": "요금이 왜 이렇게 많이 나왔는지 이유를 알고 싶다",
        "understanding_level": 0,
        "ready_to_close": False,
        "qa_result": None,
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

    if state.get("summary"):
        messages.append({
            "role": "system",
            "content": f"지금까지 상담 요약:\n{state['summary']}"
        })

    messages.append(build_customer_system_prompt(state))
    messages.extend(state["messages"][-max_turns:])

    return messages


# ===============================
# 상태 업데이트 노드
# ===============================
def state_update_node(state: State):
    """
    내부 판단 로직
    - LLM과 무관
    - 상태 기반 판단만 수행
    """
    if not state["messages"]:
        return state

    last_agent_msg = state["messages"][-1]["content"]

    update_understanding_level(state, last_agent_msg)
    update_current_goal(state)
    update_ready_to_close(state)

    return state


# ===============================
# 일반 대화 노드
# ===============================
async def customer_talk_node(state: State):
    messages = build_llm_messages(state)

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
# 요약 노드
# ===============================
async def summarize_node(state: State):
    """
    통화 종료 후 요약 생성
    - 요약이 '기억'의 역할
    - messages는 초기화
    """
    convo = ""
    for m in state["messages"]:
        role = "상담사" if m["role"] == "user" else "고객"
        convo += f"{role}: {m['content']}\n"

    prompt = f"""
다음 상담 대화를 요약하세요.

- 고객이 이해한 핵심 내용
- 여전히 남아있는 오해 또는 질문
- 상담 흐름상 도달한 결론

[대화]
{convo}
"""

    text = await openai_service.rpchat(
        messages=[{"role": "system", "content": prompt}],
        model="gpt-4o-mini",
        max_tokens=200,
    )

    state["summary"] = text

    # ❗ 과거 대화는 제거 (요약만 기억)
    state["messages"] = []

    return state


# ===============================
# QA 평가 노드
# ===============================
async def qa_evaluate_node(state: State):
    """
    QA 평가는 요약 이후 수행
    - LLM 컨텍스트와 분리
    """
    convo = ""
    for m in state.get("messages", []):
        role = "상담사" if m["role"] == "user" else "고객"
        convo += f"{role}: {m['content']}\n"

    qa_prompt = f"""
당신은 통신사 고객센터 QA 평가자입니다.

[평가 기준]
1. 문제 파악 정확성
2. 요금 설명 명확성
3. 응대 태도
4. 상담 흐름 적절성
5. 상담 종료의 자연스러움

[출력 - JSON]
{{
  "overall_score": 1~5,
  "strengths": ["장점"],
  "weaknesses": ["개선점"],
  "one_line_feedback": "한 줄 피드백"
}}

[상담 내용]
{convo}
"""

    text = await openai_service.rpchat(
        messages=[{"role": "system", "content": qa_prompt}],
        model="gpt-4o-mini",
        max_tokens=300,
    )

    state["qa_result"] = text
    return state


# ===============================
# 분기 조건
# ===============================
def decide_mode(state: State) -> Literal["talk", "close"]:
    return "close" if state["ready_to_close"] else "talk"


def should_summarize(state: State) -> Literal["summarize", "skip"]:
    return "summarize" if len(state["messages"]) >= 8 else "skip"
