from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessage
from qdrant_client import models
from app.core.config import settings
from app.services.qdrant_service import get_vector_store
from app.services.openai_service import openai_service
from app.agent.guidance.state import AgentState, AnalysisOutput, GenerateOutput
from app.agent.guidance.prompts import ANALYZE_PROMPT, QUERY_GEN_PROMPT, GENERATE_PROMPT_TEMPLATE

llm = openai_service.get_guidance_model()
vector_store = get_vector_store()

async def analyze_messages_node(state: AgentState):
  print("대화 분석 중 ==========")
  if len(state["message"]) > 5:
    last_messages = state["message"][-5:]
  else:
    last_messages = state["message"]

  # `BaseMessage` 객체에서 메시지 내용을 `.content`로 접근합니다.
  if len(last_messages[-1].content) < 2:
    print(f"skip, 분석 불필요 ==========")
    return {**state, "next_step": "skip", "resoning": "분석 불필요", "search_filter": []}

  # `BaseMessage` 객체에서 화자 정보를 `.name`으로 접근합니다.
  # `merge_transcripts`에서 AIMessage에 `name='counselor'`를 부여했으므로 이를 활용합니다.
  if isinstance(last_messages[-1], AIMessage) and last_messages[-1].name == "counselor":
    print(f"skip, 상담사가 말함 ==========")
    return {**state, "next_step": "skip", "resoning": "상담사가 말함", "search_filter": []}

  # LLM에게 RAG 필요 여부 확인
  prompt = ChatPromptTemplate.from_messages([
      ("system", ANALYZE_PROMPT),
      ("human", "## 대화 기록 (Context)\n{messages}")
  ])

  chain = prompt | llm.with_structured_output(AnalysisOutput)

  try:
    result = await chain.ainvoke({"messages":last_messages})
    print(f"{result["next_step"]}, {result["reasoning"]} ==========")
    return {
        **state,
        "reasoning": result["reasoning"],
        "next_step": result["next_step"],
        "search_filter": result["search_filter"]
    }
  except Exception as e:
    print(f"Error during analysis: {e}")
    print(f"skip, 에러 발생 스킵 ==========")
    return {**state, "next_step": "skip", "resoning": "에러 발생 스킵", "search_filter": []}




async def retrieval_node(state: AgentState):
  print("RAG 쿼리 생성 중 ==========")
  # 필터 구성
  search_filter = None
  filter_list = state.get("search_filter", [])


  # 검색 쿼리 생성
  if len(state["message"]) > 5:
    last_messages = state["message"][-5:]
  else:
    last_messages = state["message"]


  prompt = ChatPromptTemplate.from_messages([
      ("system", QUERY_GEN_PROMPT),
      ("human", "### [상담 기록]\n{last_messages}\n\n### 검색 문구:")
  ])
  chain = prompt | llm | StrOutputParser()


  query_response = await chain.ainvoke({"last_messages": last_messages})
  search_query = query_response.strip()

  all_docs = []

  for category in filter_list:
    # metadata의 category가 state["search_filter"]에 포함된 것만 검색
    search_filter = models.Filter(
        must = [
            models.FieldCondition(
                key="metadata.category",
                match=models.MatchValue(value=category)
            )
        ]
    )

    print("쿼리 생성 완료 - 검색 중 ==========")

    # 검색 수행
    category_docs = await vector_store.asimilarity_search(
      query=search_query,
      k=2,
      filter=search_filter
    )
    all_docs.extend(category_docs)


  # 결과 가공
  retrieved_context = ""
  for doc in all_docs:
    category = doc.metadata.get("category", "unknown")
    retrieved_context += f"[{category}] {doc.page_content}\n\n"

  if not retrieved_context:
    retrieved_context ="관련된 매뉴얼이나 약관 정보를 찾지 못했습니다."

  print("RAG 완료 ==========")
  return {
      **state,
      "context": retrieved_context,
      "search_query": search_query
  }




async def generate_node(state: AgentState):
  print("추천 멘트, 다음 행동 생성 중 ==========")
  # 최근 대화 5개 가져오기
  if len(state["message"]) > 5:
    last_messages = state["message"][-5:]
  else:
    last_messages = state["message"]

  # 프롬프트 생성
  prompt = ChatPromptTemplate.from_messages([
      ("system", GENERATE_PROMPT_TEMPLATE),
      ("human", ""), # 이미 시스템 프롬프트에서 입력 데이터 구조를 정의하고 있어서 빈 문자열임.
  ])

  # LLM 체인 구성
  chain = (prompt
           | llm.with_structured_output(GenerateOutput))

  # LLM 호출
  result = await chain.ainvoke({
      "customer_info": state["customer_info"],
      "context": state["context"],
      "last_messages": last_messages
  })

  print(f"{result["recommended_answer"][:40]}... ==========")
  print(f"{result["work_guide"][:40]}... ==========")

  return {
      **state,
      "recommended_answer": result["recommended_answer"].strip(),
      "work_guide": result["work_guide"].strip(),
  }

