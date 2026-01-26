import os
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_qdrant import FastEmbedSparse
from app.core.config import settings

# Qdrant 연결
if not settings.Qdrant_API_KEY or not settings.Qdrant_URL:
    print("Error: QDRANT_API_KEY 혹은 QDRANT_URL가 설정되지 않았습니다.")
    _qdrant_client = None
else:
    print("Qdrant 연결 성공")
    _qdrant_client = QdrantClient(
        url=settings.Qdrant_URL,
        api_key=settings.Qdrant_API_KEY
    )

# 임베딩 모델 준비
_dense_embeddings = None
_sparse_embeddings = None
if _qdrant_client:
    print("임베딩 모델을 로드 중입니다...")
    dense_embeddings = FastEmbedEmbeddings(
        model_name=settings.QDRANT_DENSE_EMBEDDING_MODEL,
        normalize=True
    )
    sparse_embeddings = FastEmbedSparse(
        model_name=settings.QDRANT_SPARSE_EMBEDDING_MODEL,
        sparse=True
    )

# VectorStore 연결
_vector_store = None
if _dense_embeddings and _sparse_embeddings:
    _vector_store = QdrantVectorStore(
        client=_qdrant_client,
        collection_name=settings.QDRANT_COLLECTION_NAME,
        embedding=_dense_embeddings,
        sparse_embedding=_sparse_embeddings,
        retrieval_mode=RetrievalMode.HYBRID,
        vector_name="dense",
        sparse_vector_name="sparse"
    )
    print("Qdrant VectorStore 연결 성공")

def get_vector_store():
    if _vector_store is None:
        raise Exception("Qdrant VectorStore가 초기화되지 않았습니다. API키 및 URL을 확인하세요.")
    return _vector_store