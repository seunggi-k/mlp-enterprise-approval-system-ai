import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.clients import openai_client
from app.core.config import settings
from app.services.chatbot.utils import ALLOWED_TABLES, PERSONAL_TABLES

EMPLOYEE_ALLOWED_COLUMNS = {"emp_id", "emp_name", "email", "work_phone", "msg_stat", "delegate"}

@lru_cache(maxsize=1)
def get_engine() -> Engine:
    if not settings.EMP_DB_DSN:
        raise RuntimeError("EMP_DB_DSN이 설정되지 않았습니다. 직원 DB DSN을 .env에 설정하세요.")
    return create_engine(settings.EMP_DB_DSN, pool_pre_ping=True)


def _schema_summary() -> str:
    """
    간단한 테이블/컬럼 목록을 문자열로 반환 (SQL 생성 보조용).
    """
    engine = get_engine()
    insp = inspect(engine)
    lines: List[str] = []
    allowed = {t.lower() for t in ALLOWED_TABLES}
    for table in insp.get_table_names():
        if table.lower() not in allowed:
            continue
        cols = [c["name"] for c in insp.get_columns(table)]
        lines.append(f"{table}({', '.join(cols)})")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _table_columns() -> Dict[str, set]:
    engine = get_engine()
    insp = inspect(engine)
    columns: Dict[str, set] = {}
    for table in insp.get_table_names():
        cols = {c["name"].lower() for c in insp.get_columns(table)}
        columns[table.lower()] = cols
    return columns


def _tables_have_column(tables: List[str], column: str) -> bool:
    column = column.lower()
    cols_by_table = _table_columns()
    return any(column in cols_by_table.get(t, set()) for t in tables)


def _strip_column_filter(sql: str, column: str) -> str:
    value = r"(?:[:\w]+|'[^']*'|\"[^\"]*\"|\d+)"
    updated = sql
    updated = re.sub(rf"\bwhere\s+{column}\s*=\s*{value}\s+and\s+", "where ", updated, flags=re.IGNORECASE)
    updated = re.sub(rf"\band\s+{column}\s*=\s*{value}\b", "", updated, flags=re.IGNORECASE)
    updated = re.sub(rf"\bwhere\s+{column}\s*=\s*{value}\b", "", updated, flags=re.IGNORECASE)
    updated = re.sub(r"\s{2,}", " ", updated).strip()
    updated = re.sub(r"\bwhere\s*$", "", updated, flags=re.IGNORECASE).strip()
    return updated


def _generate_select_sql(question: str, schema: str, com_id: Optional[str]) -> str:
    """
    LLM으로 안전한 SELECT 쿼리를 생성합니다. DDL/DML 금지.
    """
    def _strip_code_fence(s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = s[3:].lstrip()  # remove leading ```
            if s.lower().startswith("sql"):
                s = s[3:].lstrip()  # remove optional 'sql'
            if s.endswith("```"):
                s = s[:-3].rstrip()
        return s

    extra = f"com_id 컬럼이 존재하면 WHERE com_id = '{com_id}' 조건을 반드시 포함하세요. " if com_id else ""
    allowed_tables = ", ".join(sorted(ALLOWED_TABLES))
    prompt = (
        "다음 질문을 SQL SELECT 한 개로 변환하세요. 테이블/컬럼은 스키마에 명시된 것만 사용합니다. "
        f"허용 테이블만 사용하세요: {allowed_tables}. "
        "INSERT/UPDATE/DELETE/DDL은 금지. LIMIT 20 이하로 설정하세요. 이름/텍스트 검색은 LIKE '%키워드%'를 사용하세요. "
        f"{extra}"
        "답변은 코드펜스 없이 SQL만 출력하고, 세미콜론은 붙이지 마세요.\n\n"
        f"[스키마]\n{schema}\n\n[질문]\n{question}"
    )
    resp = openai_client.chat.completions.create(
        model=settings.RDB_MODEL,
        messages=[{"role": "system", "content": "You are a SQL assistant that only writes safe read-only queries."},
                  {"role": "user", "content": prompt}],
        temperature=0,
    )
    raw_sql = (resp.choices[0].message.content or "").strip()
    sql = _strip_code_fence(raw_sql)
    # 마지막 세미콜론은 제거해도 무방
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    print(f"[RDB] generated SQL: {sql}")
    return sql


def _is_safe_select(sql: str) -> bool:
    lowered = sql.lower()
    # 내부에서 세미콜론을 허용하지 않음(문장 분리로 오인)
    if ";" in lowered:
        return False
    if not lowered.lstrip().startswith("select"):
        return False
    banned = ["insert", "update", "delete", "drop", "alter", "truncate"]
    return not any(f" {b} " in lowered for b in banned)


def _ensure_limit(sql: str, default_limit: int = 50) -> str:
    if re.search(r"\blimit\b", sql, re.IGNORECASE):
        return sql
    limited = f"{sql} LIMIT {default_limit}"
    print(f"[RDB] limit applied -> {limited}")
    return limited


def _extract_tables(sql: str) -> List[str]:
    # 매우 단순한 FROM/JOIN 테이블명 추출
    tbls = re.findall(r"(?:from|join)\s+([`\"\w]+)", sql, flags=re.IGNORECASE)
    return [t.strip("`\"").lower() for t in tbls]


def _extract_selected_columns(sql: str) -> List[str]:
    match = re.search(r"\bselect\s+(.*?)\s+from\b", sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    raw = match.group(1)
    cols = []
    for part in raw.split(","):
        col = part.strip()
        if not col:
            continue
        col = re.sub(r"\s+as\s+.*$", "", col, flags=re.IGNORECASE).strip()
        cols.append(col)
    return cols


def _ensure_employee_columns(sql: str):
    tables = _extract_tables(sql)
    if "employee" not in tables:
        return
    selected = _extract_selected_columns(sql)
    if not selected:
        return
    for col in selected:
        if col == "*":
            raise RuntimeError("employee 테이블에서 * 선택은 허용되지 않습니다.")
        if col.endswith(".*"):
            raise RuntimeError("employee 테이블에서 테이블 전체 선택은 허용되지 않습니다.")
        if "." in col:
            col = col.split(".", 1)[1]
        if col.lower() not in EMPLOYEE_ALLOWED_COLUMNS:
            raise RuntimeError(f"employee 테이블에서 허용되지 않은 컬럼 접근: {col}")


def _ensure_allowed_tables(sql: str):
    tables = _extract_tables(sql)
    if not tables:
        return
    for t in tables:
        if t not in ALLOWED_TABLES:
            raise RuntimeError(f"허용되지 않은 테이블 접근 시도: {t}")
    print(f"[RDB] allowed tables: {tables}")


def execute_select(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    SELECT만 실행. 결과를 dict 리스트로 반환.
    """
    if not _is_safe_select(sql):
        raise RuntimeError("허용되지 않는 SQL입니다. SELECT만 지원합니다.")

    engine = get_engine()
    with engine.connect() as conn:
        print(f"[RDB] executing SQL -> {sql} params={params}")
        rows = conn.execute(text(sql), params or {}).mappings().all()
        print(f"[RDB] rows fetched={len(rows)}")
        return [dict(r) for r in rows]


def _ensure_com_filter(sql: str, com_id: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """
    com_id가 주어졌는데 SQL에 com_id 조건이 없다면 강제로 추가합니다.
    """
    params: Dict[str, Any] = {}
    if not com_id:
        return sql, params
    tables = _extract_tables(sql)
    if not _tables_have_column(tables, "com_id"):
        return _strip_column_filter(sql, "com_id"), params
    lowered = sql.lower()
    if "com_id" not in lowered:
        if " where " in lowered:
            sql = f"{sql} AND com_id = :com_id"
        else:
            sql = f"{sql} WHERE com_id = :com_id"
    params["com_id"] = com_id
    print(f"[RDB] com_id filter applied -> {sql} params={params}")
    return sql, params


def _ensure_personal_filter(sql: str, tables: List[str], emp_id: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if not emp_id:
        return sql, params
    if not any(t in PERSONAL_TABLES for t in tables):
        return sql, params
    if not _tables_have_column(tables, "emp_id"):
        return _strip_column_filter(sql, "emp_id"), params
    lowered = sql.lower()
    if "emp_id" not in lowered:
        if " where " in lowered:
            sql = f"{sql} AND emp_id = :emp_id"
        else:
            sql = f"{sql} WHERE emp_id = :emp_id"
    params["emp_id"] = emp_id
    print(f"[RDB] personal filter applied -> {sql} params={params}")
    return sql, params


def query_db_with_llm(question: str, com_id: Optional[str], emp_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    질문을 SQL로 변환 후 실행. 결과 반환.
    """
    schema = _schema_summary()
    sql = _generate_select_sql(question, schema, com_id)
    print(f"[RDB] LLM raw sql -> {sql}")
    
    # 1. LLM이 생성한 SQL에 이미 LIMIT이 있다면 제거 (문법 오류 방지)
    sql = re.sub(r"\s+limit\s+\d+\s*$", "", sql, flags=re.IGNORECASE).strip()

    _ensure_allowed_tables(sql)
    _ensure_employee_columns(sql)
    tables = _extract_tables(sql)

    # 2. 필터(com_id, emp_id)를 먼저 적용
    sql, params = _ensure_com_filter(sql, com_id)
    p_sql, p_params = _ensure_personal_filter(sql, tables, emp_id)
    params.update(p_params)
    
    # 3. 모든 필터가 적용된 '최종 SQL'에 LIMIT을 마지막으로 추가
    final_sql = _ensure_limit(p_sql)
    
    print(f"[RDB] final sql -> {final_sql} params={params}")
    return execute_select(final_sql, params)
