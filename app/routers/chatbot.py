from fastapi import APIRouter, BackgroundTasks

from app.schemas import ChatbotRunRequest
from app.services.chatbot.chatbot_service import run_chatbot

router = APIRouter(prefix="/ai/chatbot", tags=["chatbot"])


@router.post("/run")
def chatbot_run(req: ChatbotRunRequest, background: BackgroundTasks):
    """
    사내 규정 RAG 챗봇 실행. 즉시 수락 응답 후 백그라운드에서 처리.
    """
    background.add_task(run_chatbot, req)
    return {"accepted": True, "messageId": req.messageId}
