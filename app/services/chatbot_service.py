from typing import Iterable, List

from app.clients import openai_client
from app.core.config import settings
from app.schemas import ChatbotRunRequest
from app.services.callback_client import post_with_retry, validate_callback_url
from app.services.weaviate_store import search_prov_chunks
from app.services.rdb_service import query_db_with_llm, query_employee_contact_by_name


def _build_context_text(snippets: List[str]) -> str:
    if not snippets:
        return "관련 근거를 찾지 못했습니다. 질문만 참고해 답변해 주세요."
    lines = []
    for idx, snippet in enumerate(snippets, start=1):
        lines.append(f"[{idx}] {snippet}")
    return "\n".join(lines)


def _retrieve_contexts(question: str, top_k: int = 5) -> List[str]:
    """
    Weaviate에 저장된 규정 청크에서 top_k 검색.
    """
    try:
        return search_prov_chunks(question, top_k=top_k)
    except Exception as e:
        print(f"[CHATBOT] search failed: {e}")
        return []


def _stream_answer(question: str, contexts: List[str]) -> Iterable[str]:
    context_text = _build_context_text(contexts)
    user_prompt = (
        "다음 질문에 대해 제공된 근거를 우선적으로 활용하여 한국어로 간결하고 정확하게 답변해 주세요.\n"
        "근거가 불충분하거나 없으면 그 사실을 명시하세요.\n\n"
        f"[질문]\n{question}\n\n"
        f"[근거]\n{context_text}"
    )
    try:
        resp = openai_client.chat.completions.create(
            model=settings.SUM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "너는 사내 규정에 대한 RAG 챗봇이다. 근거를 우선 사용하고, 추측은 피한다.",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:
        # 스트리밍이 불가능하면 단일 호출 후 문단 단위로 분리
        resp = openai_client.chat.completions.create(
            model=settings.SUM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "너는 사내 규정에 대한 RAG 챗봇이다. 근거를 우선 사용하고, 추측은 피한다.",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        full = resp.choices[0].message.content or ""
        for para in full.split("\n\n"):
            part = para.strip()
            if part:
                yield part + "\n"


def _is_rdb_question(question: str) -> bool:
    """
    간단한 키워드로 RDB 여부 판단. 필요시 강화/LLM 분류로 대체 가능.
    """
    keywords = [
        "전화번호",
        "연락처",
        "이메일",
        "메일",
        "사번",
        "직급",
        "직책",
        "부서",
        "직원",
        "db",
        "데이터베이스",
        "몇개",
        "개수",
        "count",
        "등록된",
        "목록",
        "요금제",
        "플랜",
        "회사",
        "채팅방",
    ]
    return any(k in question for k in keywords)


def _stream_rdb_answer(req: ChatbotRunRequest) -> Iterable[str]:
    """
    DB 질의를 수행(LLM으로 SELECT 생성)하고 가벼운 모델로 답변 생성.
    """
    # 연락처/이메일/전화 키워드가 있고 이름 토큰이 있으면 우선 간단 조회 시도
    simple_keywords = ["전화", "연락처", "이메일", "메일", "번호"]
    name_token = None
    if any(k in req.question for k in simple_keywords):
        # 한글 2~4자 연속 구간을 이름 후보로 사용
        import re

        m = re.search(r"([가-힣]{2,4})", req.question)
        if m:
            name_token = m.group(1)

    rows = []
    if name_token and req.comId:
        try:
            rows = query_employee_contact_by_name(name_token, req.comId)
        except Exception as e:
            print(f"[CHATBOT] simple contact query failed: {e}")

    if not rows:
        rows = query_db_with_llm(req.question, req.comId)
    if not rows:
        # 데이터 없음 응답
        yield "해당 조건에 맞는 데이터가 없습니다.\n"
        return

    # 결과를 간단한 표 형태 텍스트로 변환
    headers = list(rows[0].keys())
    lines = [" | ".join(headers)]
    for r in rows:
        line = " | ".join(str(r.get(h, "")) for h in headers)
        lines.append(line)
    context = "\n".join(lines)

    user_prompt = (
        "아래 DB 조회 결과를 활용해 질문에 답변하세요. 정보에 없는 내용은 모른다고 답하세요.\n\n"
        f"[DB 결과]\n{context}\n\n"
        f"[질문]\n{req.question}"
    )
    try:
        resp = openai_client.chat.completions.create(
            model=settings.RDB_MODEL,
            messages=[
                {"role": "system", "content": "너는 직원 정보 질의를 간단히 답하는 보조원이다. 추측하지 말고 주어진 정보만 사용한다."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:
        resp = openai_client.chat.completions.create(
            model=settings.RDB_MODEL,
            messages=[
                {"role": "system", "content": "너는 직원 정보 질의를 간단히 답하는 보조원이다. 추측하지 말고 주어진 정보만 사용한다."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        full = resp.choices[0].message.content or ""
        for para in full.split("\n\n"):
            part = para.strip()
            if part:
                yield part + "\n"


def run_chatbot(req: ChatbotRunRequest):
    callback_url = validate_callback_url(req.callbackUrl)
    try:
        use_rdb = _is_rdb_question(req.question)
        stream: Iterable[str]
        # 1) RDB 우선 조건일 때
        if use_rdb:
            stream = _stream_rdb_answer(req)
        else:
            contexts = _retrieve_contexts(req.question, top_k=5)
            # 2) 규정 근거가 비어 있으면 DB로 폴백 시도
            if not contexts:
                stream = _stream_rdb_answer(req)
            else:
                stream = _stream_answer(req.question, contexts)

        for delta in stream:
            payload = {
                "messageId": req.messageId,
                "chunk": delta,
                "done": False,
                "success": True,
            }
            post_with_retry(callback_url, req.callbackKey, payload)

        done_payload = {"messageId": req.messageId, "done": True, "success": True}
        post_with_retry(callback_url, req.callbackKey, done_payload)
    except Exception as e:
        err_msg = str(e)
        print(f"[CHATBOT] error: {err_msg}")
        try:
            error_payload = {
                "messageId": req.messageId,
                "success": False,
                "errorMessage": err_msg,
                "done": True,
            }
            post_with_retry(callback_url, req.callbackKey, error_payload)
        except Exception as cb_err:
            print(f"[CHATBOT] callback failed after error: {cb_err}")
