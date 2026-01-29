from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, File, UploadFile, HTTPException
from fastapi.responses import FileResponse

from app.schemas.edu import JobCreateResponse, JobStatusResponse, GradeRequest, GradeResponse, NextRoundResponse
from app.services.edu_job_service import (
    create_job, run_generation, read_status, load_state, get_video_file, grade as grade_job, run_next_round
)

router = APIRouter()

@router.post("/jobs", response_model=JobCreateResponse)
async def create_edu_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    try:
        data = await file.read()
        job_id = create_job(file.filename, data)
        background_tasks.add_task(run_generation, job_id)
        return JobCreateResponse(job_id=job_id, status="queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_edu_job(job_id: str):
    st = read_status(job_id)
    if st.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="job not found")
    state = load_state(job_id)
    video_ready = bool(state.get("current_video_path"))
    quiz_ready = bool(state.get("current_quiz"))
    # expose quiz only when done
    quiz = state.get("current_quiz") if quiz_ready else None
    video_url = f"/api/v1/edu/jobs/{job_id}/video" if video_ready else None
    return JobStatusResponse(
        job_id=job_id,
        status=st.get("status",""),
        stage=st.get("stage",""),
        progress=int(st.get("progress",0)),
        round_index=int(state.get("round_index",0)),
        is_complete=bool(state.get("is_complete", False)),
        video_ready=video_ready,
        quiz_ready=quiz_ready,
        video_url=video_url,
        quiz=quiz,
        last_score=state.get("quiz_score"),
    )

@router.get("/jobs/{job_id}/video")
def download_video(job_id: str):
    p = get_video_file(job_id)
    if not p:
        raise HTTPException(status_code=404, detail="video not ready")
    return FileResponse(path=str(p), media_type="video/mp4", filename=p.name)

@router.post("/jobs/{job_id}/grade", response_model=GradeResponse)
def grade(job_id: str, req: GradeRequest):
    try:
        state = grade_job(job_id, req.user_answers)
        return GradeResponse(
            job_id=job_id,
            score=float(state.get("quiz_score",0.0)),
            is_complete=bool(state.get("is_complete", False)),
            feedback=str(state.get("quiz_feedback","")),
            mastered=len(state.get("mastered_ids",[]) or []),
            weak=len(state.get("weak_ids",[]) or []),
            unlearned=len(state.get("unlearned_ids",[]) or []),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jobs/{job_id}/next", response_model=NextRoundResponse)
def next_round(background_tasks: BackgroundTasks, job_id: str):
    state = load_state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="job not found")
    if state.get("is_complete"):
        return NextRoundResponse(job_id=job_id, status="done", message="모든 학습이 완료되었습니다.")
    # Start next round generation in background
    background_tasks.add_task(run_next_round, job_id)
    return NextRoundResponse(job_id=job_id, status="queued", message="다음 학습 세트를 생성합니다.")
