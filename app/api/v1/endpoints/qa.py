from fastapi import APIRouter

from app.schemas.qa import QAReportRequest, QAReportResponse
from app.services.qa_service import qa_service

router = APIRouter()


@router.post("/qa/report", response_model=QAReportResponse)
async def qa_report(payload: QAReportRequest):
    return await qa_service.build_report(payload)