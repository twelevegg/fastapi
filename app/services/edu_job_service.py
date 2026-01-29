from __future__ import annotations

import json, uuid, os, time, shutil
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, Optional

from app.agent.edu_video.pipeline import generate_round, grade_round

# ✅ IMPORTANT: make JOBS_ROOT absolute so chdir() won't break paths
JOBS_ROOT = Path("jobs").resolve()

def _now() -> int:
    return int(time.time())

def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

def atomic_write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

def _job_dir(job_id: str) -> Path:
    return JOBS_ROOT / job_id

def _status_path(job_id: str) -> Path:
    return _job_dir(job_id) / "status.json"

def _state_path(job_id: str) -> Path:
    return _job_dir(job_id) / "state.json"

def _quiz_path(job_id: str) -> Path:
    return _job_dir(job_id) / "quiz.json"

def _output_video_path(job_id: str) -> Path:
    # We always keep only one video file per job: output.mp4
    return _job_dir(job_id) / "output.mp4"

# ---------------------------
# Cleanup helpers
# ---------------------------

def cleanup_jobs_root(*, keep_job_id: Optional[str] = None) -> None:
    """Keep only one job folder under ./jobs.

    If keep_job_id is provided, deletes all other job folders.
    If keep_job_id is None, deletes all job folders (fresh start).
    """
    if not JOBS_ROOT.exists():
        return
    for child in JOBS_ROOT.iterdir():
        if not child.is_dir():
            # remove stray files under jobs/
            try:
                child.unlink()
            except Exception:
                pass
            continue
        if keep_job_id and child.name == keep_job_id:
            continue
        try:
            shutil.rmtree(child, ignore_errors=True)
        except Exception:
            pass

def cleanup_job_artifacts(job_id: str) -> None:
    """Within a job folder, keep only inputs/state/status. Remove previous outputs.

    Deletes:
      - output.mp4
      - edu_session_*.mp4
      - quiz.json
      - temp_*.png / temp_*.mp3 (in case any remain)
      - nested jobs/ folder (bug residue from relative JOBS_ROOT + chdir)
    """
    jd = _job_dir(job_id)
    if not jd.exists():
        return

    # ✅ remove accidental nested jobs/ folder if it exists (bug residue)
    nested = jd / "jobs"
    if nested.exists() and nested.is_dir():
        shutil.rmtree(nested, ignore_errors=True)

    # delete video artifacts
    for p in jd.glob("*.mp4"):
        try:
            p.unlink()
        except Exception:
            pass

    # delete quiz
    qp = _quiz_path(job_id)
    if qp.exists():
        try:
            qp.unlink()
        except Exception:
            pass

    # delete temp media
    for p in jd.glob("temp_*.png"):
        try:
            p.unlink()
        except Exception:
            pass
    for p in jd.glob("temp_*.mp3"):
        try:
            p.unlink()
        except Exception:
            pass

# ---------------------------
# Status / State
# ---------------------------

def write_status(job_id: str, *, status: str, stage: str = "", progress: int = 0, message: str = "") -> None:
    JOBS_ROOT.mkdir(exist_ok=True)
    jd = _job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": job_id,
        "status": status,
        "stage": stage,
        "progress": int(progress),
        "message": message,
        "updated_at": _now(),
    }
    atomic_write_json(_status_path(job_id), payload)

def read_status(job_id: str) -> Dict[str, Any]:
    p = _status_path(job_id)
    if not p.exists():
        return {"job_id": job_id, "status": "not_found", "stage": "", "progress": 0}

    # writers may be updating the file; retry a few times to avoid JSONDecodeError
    for _ in range(3):
        try:
            txt = p.read_text(encoding="utf-8").strip()
            if not txt:
                time.sleep(0.05)
                continue
            return json.loads(txt)
        except JSONDecodeError:
            time.sleep(0.05)

    return {"job_id": job_id, "status": "running", "stage": "unknown", "progress": 0}

def save_state(job_id: str, state: Dict[str, Any]) -> None:
    jd = _job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)
    safe = json.loads(json.dumps(state, ensure_ascii=False, default=str))
    atomic_write_json(_state_path(job_id), safe)

def load_state(job_id: str) -> Dict[str, Any]:
    p = _state_path(job_id)
    if not p.exists():
        return {}
    # state is written atomically, so normal read is fine
    return json.loads(p.read_text(encoding="utf-8"))

# ---------------------------
# Job lifecycle
# ---------------------------

def create_job(upload_filename: str, file_bytes: bytes) -> str:
    # Keep only the most recent job on disk
    cleanup_jobs_root(keep_job_id=None)

    job_id = uuid.uuid4().hex
    jd = _job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)

    ext = Path(upload_filename).suffix.lower()
    if ext not in [".pdf", ".pptx"]:
        ext = ".pdf"

    # ✅ store absolute path to avoid cwd/chdir issues
    input_path = (jd / f"input{ext}").resolve()
    input_path.write_bytes(file_bytes)

    write_status(job_id, status="queued", stage="queued", progress=0)
    state = {
        "job_id": job_id,
        "input_file_path": str(input_path),                 # absolute
        "persist_directory": str((jd / "chroma").resolve()), # absolute
        "round_index": 0,
    }
    save_state(job_id, state)
    return job_id

def _keep_only_latest_video(job_id: str) -> Optional[Path]:
    """After generation, keep only one mp4 file named output.mp4."""
    jd = _job_dir(job_id)

    vids = sorted(jd.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not vids:
        return None

    out = _output_video_path(job_id)
    latest = vids[0]

    # If the latest is already output.mp4, just delete others
    if latest.resolve() != out.resolve():
        try:
            # rename (atomic if same filesystem)
            os.replace(str(latest), str(out))
        except Exception:
            # fallback copy+delete
            shutil.copy2(latest, out)
            try:
                latest.unlink()
            except Exception:
                pass

    # delete any remaining mp4
    for p in jd.glob("*.mp4"):
        if p.name != out.name:
            try:
                p.unlink()
            except Exception:
                pass

    return out if out.exists() else None

def run_generation(job_id: str) -> None:
    # Keep only this job folder in ./jobs
    cleanup_jobs_root(keep_job_id=job_id)

    jd = _job_dir(job_id)
    state = load_state(job_id)

    input_path = state.get("input_file_path")
    if not input_path or not Path(input_path).exists():
        write_status(job_id, status="failed", stage="init", progress=0, message="input file not found")
        return

    # Remove previous outputs so only the latest video/quiz remain
    cleanup_job_artifacts(job_id)

    write_status(job_id, status="running", stage="initialize", progress=5, message="자료 로드/청킹 중")

    cwd = os.getcwd()
    try:
        # keep pipeline outputs under the job folder
        os.chdir(jd)

        write_status(job_id, status="running", stage="curriculum", progress=15, message="학습 단위 선정 중")
        # ✅ input_path is absolute, safe even after chdir
        state = generate_round(state, input_file_path=input_path)

        if state.get("current_quiz") is not None:
            atomic_write_json(_quiz_path(job_id), state["current_quiz"])

        write_status(job_id, status="running", stage="render", progress=85, message="영상 렌더링 중")

        # Ensure only one video file remains: output.mp4
        out_video = _keep_only_latest_video(job_id)
        if out_video and out_video.exists():
            # ✅ store stable, job-relative name for frontend (optional but clean)
            state["current_video_path"] = "output.mp4"

        save_state(job_id, state)
        write_status(job_id, status="done", stage="done", progress=100, message="완료")

    except Exception as e:
        write_status(job_id, status="failed", stage="error", progress=0, message=str(e))
        raise
    finally:
        try:
            os.chdir(cwd)
        except Exception:
            pass

def run_next_round(job_id: str) -> None:
    # Keep only this job folder in ./jobs
    cleanup_jobs_root(keep_job_id=job_id)

    state = load_state(job_id)
    if state.get("is_complete"):
        write_status(job_id, status="done", stage="done", progress=100, message="이미 모든 학습 완료")
        return

    # increment round and overwrite outputs
    state["round_index"] = int(state.get("round_index", 0)) + 1
    save_state(job_id, state)

    run_generation(job_id)

def grade(job_id: str, user_answers: list[int]) -> Dict[str, Any]:
    # Keep only this job folder in ./jobs
    cleanup_jobs_root(keep_job_id=job_id)

    state = load_state(job_id)
    if not state.get("current_quiz"):
        qp = _quiz_path(job_id)
        if qp.exists():
            state["current_quiz"] = json.loads(qp.read_text(encoding="utf-8"))
    if not state.get("current_quiz"):
        raise ValueError("quiz not ready")

    write_status(job_id, status="running", stage="grading", progress=95, message="채점/해설 생성 중")
    state = grade_round(state, user_answers=user_answers)
    save_state(job_id, state)
    write_status(job_id, status="done", stage="done", progress=100, message="채점 완료")
    return state

def get_video_file(job_id: str) -> Optional[Path]:
    """
    Prefer output.mp4. Fallback: pick latest mp4 in the correct job folder.
    With JOBS_ROOT absolute, this works regardless of current working directory.
    """
    p = _output_video_path(job_id)
    if p.exists():
        return p
    jd = _job_dir(job_id)
    vids = sorted(jd.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True)
    return vids[0] if vids else None
