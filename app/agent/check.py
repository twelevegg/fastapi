
import os
from dotenv import load_dotenv
from typing import TypedDict, List
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from qdrant_client import QdrantClient, models
from langgraph.graph import StateGraph, START, END

load_dotenv()

# 1. 설정 정보 (ingest.py와 동일하게 유지)
COLLECTION_NAME = "cs_guideline"
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# 2. 임베딩 모델 준비 (ingest.py와 동일해야 검색 가능)
print("임베딩 모델을 로드 중입니다...")
dense_embeddings = FastEmbedEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", 
    normalize=True
)
sparse_embeddings = FastEmbedSparse(
    model_name="Qdrant/bm25", 
    sparse=True
)

# 3. Qdrant 클라이언트 및 VectorStore 연결
client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

# LangChain VectorStore 래퍼 설정 (Hybrid 검색 모드)
vector_store = QdrantVectorStore(
    client=client,
    collection_name=COLLECTION_NAME,
    embedding=dense_embeddings,
    sparse_embedding=sparse_embeddings,
    retrieval_mode=RetrievalMode.HYBRID,
    vector_name="dense",
    sparse_vector_name="sparse",
)

# 4. LangGraph 설정

class AgentState(TypedDict):
    question: str
    results: List[dict]

def retrieve(state: AgentState):
    question = state["question"]
    print(f"Retrieving for question: {question}")
    
    # 1. 검색 (Hybrid)
    results = vector_store.similarity_search(question, k=3)
    
    # 2. 결과 포맷팅
    response_data = []
    for res in results:
        response_data.append({
            "source": res.metadata.get("source"),
            "category": res.metadata.get("category"),
            "title": res.metadata.get("title"),
            "content": res.page_content
        })
        
    return {"results": response_data}

# 그래프 구성
workflow = StateGraph(AgentState)
workflow.add_node("retrieve", retrieve)
workflow.add_edge(START, "retrieve")
workflow.add_edge("retrieve", END)

# 그래프 컴파일
graph_app = workflow.compile()

def get_agent_response(question: str):
    """
    LangGraph를 실행하여 결과를 반환합니다.
    """
    inputs = {"question": question}
    result = graph_app.invoke(inputs)
    return result["results"]

def print_results(results, query_type=""):
    print(f"\n[{query_type}] 검색 결과 ({len(results)}건):")
    print("-" * 50)
    for i, res in enumerate(results):
        print(f"   출처: {res.get('source')}")
        print(f"   카테고리: {res.get('category')}")
        print(f"   제목: {res.get('title')}")
        print(f"   내용: {res.get('content')[:150]}...")
        print("-" * 50)

# 5. 테스트 쿼리 실행 함수 (내부 테스트용)
def run_tests():
    # 시나리오 1: 일반적인 질문 검색 (Hybrid)
    query1 = "해지 시 위약금은 얼마나 나와?"
    print(f"\n>>> 질문 1: {query1}")
    results1 = get_agent_response(query1)
    print_results(results1, "LangGraph Hybrid Search")

if __name__ == "__main__":
    if client.collection_exists(COLLECTION_NAME):
        run_tests()
    else:
        print(f"컬렉션 '{COLLECTION_NAME}'이 존재하지 않습니다. ingest.py를 먼저 실행하세요.")