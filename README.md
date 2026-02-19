# AIVLE School Final Project: AI CS Training Platform
**(AI 기반 고객 응대 교육 및 시뮬레이션 플랫폼)**

본 프로젝트는 신입 상담사 및 재직자를 위한 **AI 기반 통합 교육 및 훈련 플랫폼**입니다.
최신 생성형 AI 기술(LLM, RAG, TTS, STT)을 활용하여, 실제 상담 환경과 유사한 시뮬레이션, 맞춤형 롤플레잉, 그리고 자동화된 교육 콘텐츠 생성 기능을 제공합니다.

## 📌 기획 의도
- **실전 같은 훈련 환경 제공**: 단순 이론 교육을 넘어, AI 고객과의 실시간 대화 시뮬레이션을 통해 상담 역량을 강화합니다.
- **교육 콘텐츠 자동화**: 기존 매뉴얼(PDF, PPTX)을 AI가 분석하여 학습 영상 및 퀴즈를 자동으로 생성함으로써 교육 자료 제작 효율을 극대화합니다.
- **맞춤형 피드백**: 상담 내용을 실시간으로 분석하고 평가하여, 개인화된 피드백과 개선점을 제시합니다.

## 🚀 핵심 기능 (Core Features)

### 1. AI 상담 시뮬레이션 (Simulation)
- **실시간 대화 시뮬레이션**: WebSocket을 활용하여 상담사와 고객(AI) 간의 실시간 음성/텍스트 대화를 시뮬레이션합니다.
- **다양한 시나리오**: KT 상담 시나리오(예: 요금제 변경, 결합 상품 문의 등)를 바탕으로 정교한 고객 페르소나를 AI가 연기합니다.
- **자동 평가**: 시뮬레이션 종료 후 상담 내용을 분석하여 응대 적절성을 평가합니다.

### 2. 교육 콘텐츠 자동 생성 (Edu-Job)
- **자료 업로드 및 분석**: PDF나 PPTX 형태의 교육 자료를 업로드하면, AI가 내용을 분석하고 청킹(Chunking)하여 지식 베이스를 구축합니다.
- **학습 영상 생성**: 분석된 내용을 바탕으로 대본을 작성하고, TTS와 이미지 생성을 결합하여 교육 영상을 자동으로 제작합니다.
- **퀴즈 생성 및 채점**: 학습 내용에 기반한 퀴즈를 자동으로 생성하고, 사용자의 풀이 결과를 채점 및 해설합니다.

### 3. AI 롤플레잉 (Role Play)
- **페르소나 기반 훈련**: 다양한 성격과 상황을 가진 AI 페르소나(강성 고객, 일반 고객 등)와 1:1 롤플레잉을 진행할 수 있습니다.
- **RAG 기반 응대**: 상담 도중 필요한 정보를 Qdrant/ChromaDB 벡터 데이터베이스에서 실시간으로 검색하여 정확한 가이드를 제공하거나 AI가 활용합니다.

### 4. 상담 가이드 및 품질 관리 (Guidance & QA)
- **실시간 가이드**: 상담 진행 중 AI가 대화 문맥을 파악하여 추천 답변이나 필요한 정보를 실시간으로 제공합니다.
- **품질 관리(QA)**: 상담 데이터를 종합적으로 분석하여 서비스 품질을 모니터링하고 리포트를 생성합니다.

## 🛠 기술 스택 (Tech Stack)

### Backend
- **Framework**: FastAPI (Python 3.12+)
- **Server**: Uvicorn
- **API**: RESTful API, WebSocket (실시간 통신)

### AI & Data
- **LLM Orchestration**: LangChain, LangGraph
- **LLM Model**: OpenAI (GPT-4o / GPT-3.5 Turbo)
- **Vector DB**: Qdrant (Guidance/RAG), ChromaDB (Local/Temp usage)
- **Audio/Video**: 
    - **TTS**: gTTS (Google Text-to-Speech)
    - **Video Gen**: MoviePy (영상 렌더링 및 편집)
    - **STT**: Whisper (또는 호환 API)

### Infrastructure & DevOps
- **Storage**: AWS S3 (교육 자료, 생성된 영상/이미지 저장)
- **Containerization**: Docker
- **Environment**: Python dotenv, Pydantic Settings

## 📂 프로젝트 구조 (Project Structure)

```bash
📦 fastapi
 ┣ 📂 app
 ┃ ┣ 📂 api             # API 엔드포인트 (v1)
 ┃ ┃ ┣ 📂 endpoints     # chat, stt, rp, edu, simulation 등 기능별 라우터
 ┃ ┣ 📂 agent           # AI 에이전트 로직 (LangGraph, RAG 등)
 ┃ ┃ ┣ 📂 edu_video     # 교육 영상 생성 에이전트
 ┃ ┃ ┣ 📂 rp            # 롤플레잉 에이전트
 ┃ ┣ 📂 core            # 설정(Config), 보안 등
 ┃ ┣ 📂 schemas         # Pydantic 데이터 모델 (DTO)
 ┃ ┣ 📂 services        # 비즈니스 로직 (Service Layer)
 ┃ ┃ ┣ 📜 edu_job_service.py   # 교육 콘텐츠 생성 로직
 ┃ ┃ ┣ 📜 simulation_service.py # 시뮬레이션 로직
 ┃ ┃ ┗ ...
 ┣ 📜 Dockerfile        # Docker 빌드 설정
 ┣ 📜 requirements.txt  # 의존성 패키지 목록
 ┗ 📜 main.py           # 애플리케이션 진입점
```

## 💻 설치 및 실행 (User Guide)

### 1. 사전 요구사항 (Prerequisites)
- Python 3.12 이상
- Docker (선택 사항)
- OpenAI API Key, AWS S3 계정, Qdrant 인스턴스

### 2. 환경 변수 설정 (.env)
프로젝트 루트에 `.env` 파일을 생성하고 다음 정보를 입력하세요.
```env
OPENAI_API_KEY=sk-...
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_BUCKET_NAME=...
QDRANT_URL=...
...
```

### 3. 로컬 실행
```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn app.main:app --reload
```
서버가 시작되면 `http://localhost:8000/docs`에서 Swagger Documentation을 확인할 수 있습니다.

배포 환경은 `https://api.csnavigator.cloud/docs`입니다.

### 4. Docker 실행
```bash
docker build -t aivle-fastapi .
docker run -p 8000:8000 --env-file .env aivle-fastapi
```
