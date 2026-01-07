import json
from typing import Iterable, List, Optional

from app.clients import openai_client
from app.core.config import settings
from app.schemas import ChatHistoryMessage
from app.services.chatbot.utils import _history_to_text, clean_json_string

_ACTIONS = [
    {"id": "NAV_MAIL_COMPOSE", "label": "메일 작성", "requiredParams": []},
    {"id": "NAV_MY_RESERVATIONS", "label": "내 예약 조회", "requiredParams": []},
    {"id": "NAV_TODAY_SCHEDULE", "label": "오늘 일정", "requiredParams": []},
    {"id": "NAV_APPROVAL_DRAFT", "label": "결재 작성", "requiredParams": []},
]


def _suggest_action(question: str, history: List[ChatHistoryMessage] | None, db_text: str, rag_text: str) -> Optional[dict]:
    action_list = "\n".join(
        [f"- {a['id']} (params: {a['requiredParams']})" for a in _ACTIONS]
    )
    history_text = _history_to_text(history)
    user_block = (
        f"[이전 대화]\n{history_text}\n\n[질문]\n{question}\n\n[DB]\n{db_text}\n\n[RAG]\n{rag_text}"
        if history_text
        else f"[질문]\n{question}\n\n[DB]\n{db_text}\n\n[RAG]\n{rag_text}"
    )
    system_prompt = (
        "아래 액션 목록 중 적절한 이동 액션을 하나 선택하고 JSON만 출력하세요. "
        "이메일 관련 질문이 들어오면 메일 작성 액션을 선택합니다. "
        "에약 관련 질문이 들어오면 내 예약 조회 액션을 선택합니다 "
        "일정 관련 질문이 들어오면 오늘 일정 액션을 선택합니다 "
        "결재 작성 질문이 들어오면 결재 작성을 선택합니다 "
        "적절한 액션이 없으면 null을 출력합니다. "
        
        "형식: {\"actionId\": \"...\", \"params\": {\"key\": \"val\"}} 또는 null. "
        f"액션 목록:\n{action_list}"
        "이전 대화는 보조 정보이며, 현재 질문/DB/RAG 근거를 우선하라."
    )
    try:
        resp = openai_client.chat.completions.create(
            model=settings.RDB_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_block},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content or "null"
        print(f"[SYNTH] action raw response: {raw!r}")
        raw = clean_json_string(raw)
        data = json.loads(raw)
        print(f"[SYNTH] action parsed: {data}")
        if data is None:
            return None
        if isinstance(data, dict) and "actionId" in data:
            if not data.get("params") or not isinstance(data["params"], dict):
                data["params"] = {}
            return data
    except Exception as e:
        print(f"[SYNTH] action suggest failed: {e}")
    return None


def stream_final_answer(
    question: str,
    history: List[ChatHistoryMessage] | None,
    db_text: str,
    rag_text: str,
    answer_style: str | None,
    mode: str,
) -> Iterable[dict]:
    """
    DB와 RAG 근거를 모두 사용해 최종 답변을 스트리밍한다.
    반환: {"chunk": str} 또는 마지막에는 {"done": True, "action": {...}} 형태
    """
    style_hint = f"답변 스타일: {answer_style}" if answer_style else ""
    user_prompt = (
        "아래 DB 결과와 규정 근거를 활용해 한국어로 간결하고 정확하게 답변하세요. "
        "DB는 사실 데이터, RAG는 규정/정책 근거입니다. 정보가 없으면 모른다고 말하세요. "
        "이전 대화는 보조 정보이며, 현재 질문/DB/RAG 근거를 우선하라."
        f"{style_hint}\n\n"
        f"[질문]\n{question}\n\n"
        f"[DB 결과]\n{db_text or '(없음)'}\n\n"
        f"[규정 근거]\n{rag_text or '(없음)'}"
    )
    
    print("question + db_text + rag_ text "+ question+" "+db_text+ " "+ rag_text)
    try:
        resp = openai_client.chat.completions.create(
            model=settings.SUM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 사내 전자결재/그룹웨어 챗봇이다. DB 결과는 사실, 규정 근거는 정책이다. "
                        "출처가 없는 내용은 추측하지 말고, 필요시 근거/데이터 부족을 명시한다."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield {"chunk": delta}
        action = _suggest_action(question, history, db_text, rag_text)
        yield {"done": True, "action": action}
    except Exception:
        resp = openai_client.chat.completions.create(
            model=settings.SUM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 사내 전자결재/그룹웨어 챗봇이다. DB 결과는 사실, 규정 근거는 정책이다. "
                        "출처가 없는 내용은 추측하지 말고, 필요시 근거/데이터 부족을 명시한다."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        full = resp.choices[0].message.content or ""
        for para in full.split("\n\n"):
            part = para.strip()
            if part:
                yield {"chunk": part + "\n"}
        action = _suggest_action(question, history, db_text, rag_text)
        yield {"done": True, "action": action}
