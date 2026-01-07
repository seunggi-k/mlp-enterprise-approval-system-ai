import re
from typing import Mapping

ALLOWED_TABLES = {
    "approval_line",
    "attendance",
    "board",
    "corporate_car",
    "corporate_car_reservation",
    "meeting_room",
    "meeting_room_reservation",
    "shared_equipment",
    "shared_equipment_reservation",
    "emp_schedule",
    "employee",
    "todo_list",
    "mail",
    "meeting",
    "meeting_emp",
    "schedule",
}

PERSONAL_TABLES = {"todo_list", "mail", "attendance", "emp_schedule"}


def _history_to_text(history) -> str:
    if not history:
        return ""
    lines = []
    for m in history:
        if isinstance(m, Mapping):
            role = str(m.get("role", "")).lower()
            content = m.get("content", "")
        else:
            role = str(getattr(m, "role", "")).lower()
            content = getattr(m, "content", "")
        if not content:
            continue
        prefix = "User" if role.startswith("user") else "Assistant"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


def clean_json_string(raw: str | None, default: str = "{}") -> str:
    if not raw:
        return default
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()
    return text or default
