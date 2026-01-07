from datetime import datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy import text

from app.services.chatbot.rdb_service import (
    get_engine,
    query_db_with_llm
)
from app.services.chatbot.utils import ALLOWED_TABLES, PERSONAL_TABLES


def _limit_clause(limit: int | None, default: int = 50) -> str:
    lim = limit or default
    return f" LIMIT {min(lim, default)}"



def format_rows(rows: List[Dict[str, Any]], max_rows: int = 10) -> str:
    if not rows:
        return ""
    sample = rows[:max_rows]
    headers = list(sample[0].keys())
    lines = [" | ".join(headers)]
    for r in sample:
        line = " | ".join(str(r.get(h, "")) for h in headers)
        lines.append(line)
    if len(rows) > max_rows:
        lines.append(f"...({len(rows) - max_rows} more)")
    return "\n".join(lines)
