OVERALL_QA_PROMPT = """
당신은 통신사 고객센터 QA 평가자입니다.
아래 상담 내용을 '신입 상담사 교육' 관점에서 평가하세요.

[평가 기준(각 1~5점)]
1) problem_understanding: 문제 파악 정확성
2) explanation_clarity: 요금/원인 설명의 명확성(구체성 포함)
3) tone_and_attitude: 응대 태도/공감/감정 대응
4) flow_control: 흐름/질문 순서/불필요한 반복 여부
5) closing: 마무리(요약/확인/다음 행동 안내 등)

[참고 메모리(있다면)]
{memory_text}

[상담 내용(전체)]
{convo}

[출력 - JSON만]
{{
  "overall_score": 1~5,
  "category_scores": {{
    "problem_understanding": 1~5,
    "explanation_clarity": 1~5,
    "tone_and_attitude": 1~5,
    "flow_control": 1~5,
    "closing": 1~5
  }},
  "strengths": ["장점 2~4개"],
  "weaknesses": ["개선점 2~4개"],
  "one_line_feedback": "한 줄 총평(학습자에게 건설적으로)"
}}
""".strip()


TURN_LEVEL_QA_PROMPT = """
너는 통신사 고객센터의 '전문 상담사'이자 '교육용 QA 코치'다.

[고객 발화]
{customer_utterance}

[상담사 실제 발화]
{agent_utterance}

[참고 메모리(있다면)]
{memory_text}

[지시]
1) 이 상황에서 전문 상담사라면 어떤 답변이 가장 적절한지 먼저 작성(1~3문장).
2) 실제 발화를 기준 답변과 비교해 항목별 1~5점 평가:
   - accuracy: 정확성/정책·원인 적합성
   - clarity: 명확성/구체성/다음 행동 안내
   - empathy: 공감/감정 대응
3) 이 문장이 **잘한 문장이라면**, 왜 좋은 응대였는지 한 문장으로 설명하라.
4) 이 문장이 **고쳐야 할 문장이라면**, 왜 아쉬운지와 개선 방향을 한 문장으로 설명하라

[출력 - JSON만]
{{
  "expert_recommended_response": "모범 답변(1~3문장)",
  "scores": {{
    "accuracy": 1~5,
    "clarity": 1~5,
    "empathy": 1~5
  }},
  "positive_feedback": "이 문장이 잘한 응대인 이유 (해당되는 경우에만 작성)",
  "negative_feedback": "이 문장에서 개선이 필요한 이유 (해당되는 경우에만 작성)"
}}
""".strip()


GROWTH_POINT_PROMPT = """
너는 '신입 상담사 교육 코치'다.
다음 결과를 바탕으로 다음 RP에서 가장 효과가 큰 '성장포인트'를 1~2개만 뽑아라.
성장포인트는 반드시 5요소로 작성한다:
- focus(무엇을)
- when(언제)
- why(왜)
- how(어떻게)
- example_sentence(예시 멘트)

[참고 메모리]
{memory_text}

[종합 평가(전체 대화 기반)]
{overall_json}

[잘한 문장 TOP]
{top_block}

[고쳐야 할 문장 BOTTOM]
{bottom_block}

[출력 - JSON만]
{{
  "growth_points": [
    {{
      "focus": "...",
      "when": "...",
      "why": "...",
      "how": "...",
      "example_sentence": "..."
    }}
  ]
}}
""".strip()
