# FastAPI AI Service

## 실행 방법

### 1. 환경 설정 및 의존성 설치

```bash
# 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일을 추가해 OpenAI API Key 입력.
g
```ini
OPENAI_API_KEY=[your_openai_api_key_here]
PROJECT_NAME="FastAPI AI Service"
VERSION="1.0.0"
API_V1_STR="/api/v1"
QDRANT_URL = [노션에 있음]
QDRANT_API_KEY = [노션에 있음]
QDRANT_COLLECTION_NAME = "cs_guideline"
QDRANT_DENSE_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
QDRANT_SPARSE_EMBEDDING_MODEL = "Qdrant/bm25"
```

### 3. 서버 실행

```bash
uvicorn app.main:app --reload
```

### 4. 테스트

브라우저에서 다음 주소로 접속하여 API 문서를 확인하고 테스트할 수 있습니다.

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
