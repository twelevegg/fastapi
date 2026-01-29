import os
import json
import glob
import re
from pathlib import Path
from .state import AgentState
from .utils_file import load_and_chunk_files
from .utils_media import create_video_segment
from .rag_engine import RAGEngine
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# ✅ 비용을 줄이면서도 충분히 빠른 모델로 변경
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

def _clean_slide_title(title: str) -> str:
    t = str(title or "").strip()
    # "slide 0 : ", "Slide 2 -", "슬라이드 3:" 같은 접두어 제거
    t = re.sub(r"^\s*(?:slide|슬라이드)\s*\d+\s*[:\-–—]\s*", "", t, flags=re.IGNORECASE)
    # 혹시 "0: 제목"처럼 숫자만 오는 경우도 제거
    t = re.sub(r"^\s*\d+\s*[:\-–—]\s*", "", t)

    # 공백 정리
    t = re.sub(r"\s+", " ", t).strip()

    # ✅ 제목 길이 제한 (한 줄 가독성 확보)
    # - 강의 슬라이드/영상에서 제목이 길면 레이아웃이 깨지므로 상한을 둡니다.
    # - 한글 기준 권장 18~28자, 상한 32자
    MAX_TITLE_LEN = 32

    if len(t) > MAX_TITLE_LEN:
        # 1) 구분자(":", "-", "|" 등) 앞부분을 우선 사용
        splitters = [" | ", " - ", " – ", " — ", " : ", ":", "-", "|", "•"]
        for sp in splitters:
            if sp in t:
                cand = t.split(sp, 1)[0].strip()
                if cand and len(cand) <= MAX_TITLE_LEN:
                    t = cand
                    break

    if len(t) > MAX_TITLE_LEN:
        # 2) 괄호/대괄호 안 부가설명 제거
        t2 = re.sub(r"\s*[\(\[\{].*?[\)\]\}]\s*", " ", t).strip()
        t2 = re.sub(r"\s+", " ", t2)
        if len(t2) <= MAX_TITLE_LEN and t2:
            t = t2

    if len(t) > MAX_TITLE_LEN:
        # 3) 최후: 말줄임표로 자르기
        t = t[: MAX_TITLE_LEN - 1].rstrip() + "…"

    return t

def node_initialize(state: AgentState):
    print("--- [Process] 데이터 로드 및 청킹 ---")
    # ✅ 단일 파일 입력 전제
    input_file_path = state.get("input_file_path")
    if input_file_path and os.path.exists(str(input_file_path)):
        selected_file = str(input_file_path)
        print(f"✅ 입력 파일(지정): {selected_file}")
        files = [selected_file]
    else:
        # ✅ 단일 파일 입력 전제(현재 작업 디렉토리 스캔)
        files = glob.glob("*.pdf") + glob.glob("*.pptx")
        if not files:
            print("경고: 학습할 파일을 찾을 수 없습니다. (현재 폴더에 .pdf 또는 .pptx 1개를 두고 실행해 주세요.)")
            return {"is_complete": True}

        # 여러 개가 있으면 최신 파일 1개만 사용
        files = sorted(files, key=lambda p: os.path.getmtime(p), reverse=True)
        selected_file = files[0]
        if len(files) > 1:
            print(f"⚠️ 여러 파일이 감지되어 최신 파일 1개만 사용합니다: {selected_file}")
        else:
            print(f"✅ 입력 파일: {selected_file}")
    if len(files) > 1:
        print(f"⚠️ 여러 파일이 감지되어 최신 파일 1개만 사용합니다: {selected_file}")
    else:
        print(f"✅ 입력 파일: {selected_file}")
    
    knowledge_base = load_and_chunk_files([selected_file])
    return {
        "knowledge_base": knowledge_base,
        "unlearned_ids": [u['id'] for u in knowledge_base],
        "weak_ids": [],
        "mastered_ids": [],
        "is_complete": False
    }

def node_curriculum_manager(state: AgentState):
    print("--- [Process] 단일 파일 커리큘럼 구성 ---")
    # 단일 파일이므로 파일 타입별 3:7 샘플링 대신, 남은 청크에서 순차적으로 배치 구성
    order = state.get("_selection_order", "weak_first")
    if order == "unlearned_first":
        remaining_ids = state.get('unlearned_ids', []) + state.get('weak_ids', [])
    else:
        remaining_ids = state.get('weak_ids', []) + state.get('unlearned_ids', [])
    remaining_ids = [i for i in remaining_ids if i in {u['id'] for u in state['knowledge_base']}]

    target_size = 14  # 7~10분 분량을 위한 청크 수(대략)
    current_batch_ids = remaining_ids[:target_size]

    if not current_batch_ids:
        return {"is_complete": True}
    return {"current_batch_ids": current_batch_ids}

def node_content_creator(state: AgentState):
    print(f"--- [Process] 맞춤형 교육 시퀀스 생성 (총 {len(state['current_batch_ids'])}개 청크) ---")
    
    target_ids = state['current_batch_ids']
    chunks = [u['content'] for u in state['knowledge_base'] if u['id'] in target_ids]
    chunk_groups = [chunks[i:i+2] for i in range(0, len(chunks), 2)]
    
    full_context = ""
    for idx, group in enumerate(chunk_groups):
        full_context += f"\n[Slide {idx+1} Data]\n" + "\n".join(group)

    prompt = ChatPromptTemplate.from_template(
        """
        당신은 기업 교육 전문 강사입니다. 주어진 자료를 분석하여 '브랜드'를 식별하고 자연스러운 강의 시퀀스를 만드세요.

        [지시사항]
        1. **브랜드 식별**: 자료에 나오는 기업이나 통신사 이름(예: SKT, KT, LG U+ 등)을 정확히 파악하여 'brand' 필드에 넣으세요. 만약 명시되지 않았다면 빈칸으로 놔두세요.
        2. **자연스러운 연결**: Slide 1만 인사를 하고, Slide 2부터는 "다음으로", "연결해서 설명드리면" 등 자연스러운 전환어를 사용하세요. 절대 매 슬라이드마다 인사를 반복하지 마세요.
        3. **내용 풍성함**: 각 슬라이드(summary)는 반드시 5개 이상의 불렛포인트로 작성하세요. 자료가 부족하면 해당 개념에 대한 '상담 예시'나 '현장 Q&A'를 추가하여 분량을 채우세요.
        4. **대본 분량**: 슬라이드당 1분 내외(150자 이상)의 상세 대본을 작성하세요.
        5. **제목 규칙**: title은 한 줄로 보이도록 **32자 이내**로 작성하고, 핵심 키워드 중심으로 짧게 만드세요. (긴 부가설명/예시는 summary로 옮기기)

        [자료]
        {context}

        형식: JSON 리스트 [{{ "brand": "식별된이름", "title": "제목", "summary": "내용1\\n내용2...", "text": "대본..." }}]
        """
    )
    
    response = (prompt | llm).invoke({"context": full_context})
    
    try:
        clean_res = response.content.replace("```json", "").replace("```", "").strip()
        script_segments = json.loads(clean_res)
        if isinstance(script_segments, list):
            for seg in script_segments:
                if isinstance(seg, dict) and "title" in seg:
                    seg["title"] = _clean_slide_title(seg.get("title", ""))
    except:
        script_segments = [{"brand": "Education", "title": "교육 세션", "summary": "내용 요약", "text": response.content}]

    session_idx = len(state.get('mastered_ids', []))
    video_filename = f"edu_session_{session_idx}.mp4"

    # ✅ PPT 없이 이미지 기반으로 바로 영상만 생성
    create_video_segment(script_segments, output_filename=video_filename)
    
    return {
        "current_video_path": video_filename,
        "current_ppt_path": None,
        "current_script": str(script_segments)
    }

# --- 4. 퀴즈 생성 노드 ---
def node_quiz_generator(state: AgentState):
    print("--- [Process] 퀴즈 생성 ---")
    
    target_contents = [u['content'] for u in state['knowledge_base'] if u['id'] in state['current_batch_ids']]
    context_text = "\n".join(target_contents)
    
    # 문제 수: 배치 크기에 비례 (약 2~3배수)
    num_questions = 10
    
    prompt = ChatPromptTemplate.from_template(
        """
        아래 교육 내용을 바탕으로 {num}개의 4지 선다형 퀴즈를 만들어주세요.
        통신사 업무와 관련된 뉘앙스를 살려주세요.
        출력 포맷(JSON List): [{{ "question": "문제", "options": ["보기1", "보기2", "보기3", "보기4"], "correct_answer": 정답인덱스(0-3), "related_chunk_index": 관련된_내용_순서_인덱스 }}]
        
        내용:
        {context}
        """
    )
    chain = prompt | llm
    response = chain.invoke({"context": context_text, "num": num_questions})
    
    try:
        quiz_data = json.loads(response.content.replace("```json", "").replace("```", "").strip())
    except:
        quiz_data = [] # 에러 처리 생략
        
    return {"current_quiz": quiz_data}

#  채점

def node_grader(state: AgentState):
    print("\n" + "="*20 + " [채점 및 상세 피드백 시작] " + "="*20)
    
    quiz_list = state['current_quiz']
    user_answers = state['user_answers']
    knowledge_base = state['knowledge_base']
    
    rag = RAGEngine(knowledge_base, collection_name=str(state.get("job_id","edu_rag")), persist_directory=state.get("persist_directory"))
    
    score = 0
    feedback_details = []
    wrong_chunk_ids = set()
    mastered_ids_in_session = []

    for i, (q, u_ans) in enumerate(zip(quiz_list, user_answers)):
        is_correct = (q['correct_answer'] == u_ans)
        
        # RAG를 통해 근거 자료 확보
        search_query = f"{q['question']} {q['options'][q['correct_answer']]}"
        contexts = rag.get_detailed_context(search_query)

        # 컨텍스트를 LLM에 주기 좋게 간단히 포맷팅
        def _fmt_ctx(c):
            src = Path(str(c.get('source', ''))).name
            pg = c.get('page')
            pg_txt = f"{pg}P" if pg not in (None, "?") else "?P"
            excerpt = str(c.get('content', '')).replace("\n", " ").strip()
            if len(excerpt) > 260:
                excerpt = excerpt[:260] + "..."
            return f"- {src} {pg_txt}: {excerpt}"
        formatted_contexts = "\n".join([_fmt_ctx(c) for c in contexts])
        
        # LLM에게 상세 해설 요청
        explanation_prompt = f"""
당신은 통신사 CS 교육 컨설턴트입니다. 아래 퀴즈 문제에 대한 피드백을 **반드시 지정된 형식**으로 작성하세요.

[문제]: {q['question']}
[정답]: {q['options'][q['correct_answer']]}
[사용자 답변]: {q['options'][u_ans] if isinstance(u_ans, int) else u_ans}
[결과]: {"정답" if is_correct else "오답"}

[참고자료 후보]:
{formatted_contexts}

[출력 형식(반드시 준수)]:
해설: (정답인 이유를 2~4문장으로 설명. 오답이면 왜 헷갈렸는지도 1문장 추가)
참고자료: (반드시 '파일명'과 '페이지(P)'를 포함해서 1~2개만 고르기. 아래처럼 작성)
 - 참고자료 <파일명> <페이지>P를 확인해보면 "<핵심 근거 구절>" 라고 되어 있어요.
"""
        
        explanation_res = llm.invoke(explanation_prompt).content
        
        # 피드백 저장
        result_text = "✅ [정답]" if is_correct else "❌ [오답]"
        feedback_details.append(f"{i+1}번 문제: {result_text}\n{explanation_res}\n" + "-"*50)

        if is_correct:
            score += 1
            # 맞은 문제와 연결된 지식 단위 ID 저장 (chunk_index가 있다고 가정)
            idx = q.get('related_chunk_index', 0)
            if idx < len(state['current_batch_ids']):
                mastered_ids_in_session.append(state['current_batch_ids'][idx])
        else:
            idx = q.get('related_chunk_index', 0)
            if idx < len(state['current_batch_ids']):
                wrong_chunk_ids.add(state['current_batch_ids'][idx])

    final_score = (score / len(quiz_list)) * 100 if quiz_list else 0
    
    # 화면 출력
    for feedback in feedback_details:
        print(feedback)
        
    print(f"\n🎯 최종 점수: {final_score}점")

    # ✅ 상태 업데이트(weak/unlearned/mastered)
    new_mastered = list(dict.fromkeys(state.get('mastered_ids', []) + mastered_ids_in_session))
    new_weak = list(dict.fromkeys(state.get('weak_ids', []) + list(wrong_chunk_ids)))
    # 배치에 포함된 mastered/weak는 unlearned에서 제거
    to_remove = set(mastered_ids_in_session) | set(wrong_chunk_ids)
    new_unlearned = [i for i in state.get('unlearned_ids', []) if i not in to_remove]

    return {
        "mastered_ids": new_mastered,
        "weak_ids": new_weak,
        "unlearned_ids": new_unlearned,
        "quiz_score": final_score,
        "quiz_feedback": "\n\n".join(feedback_details)
    }