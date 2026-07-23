from app.services.openai.ids import msg_id

_OUTPUT_ROLES = {"assistant"}


def flatten_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join((p.get("text") or "") for p in content if isinstance(p, dict)).strip()
    return ""


def item_from_message(msg) -> dict:
    part_type = "output_text" if msg.role in _OUTPUT_ROLES else "input_text"
    return {
        "id": msg_id(msg.id),
        "type": "message",
        "role": msg.role,
        "status": "completed",
        "content": [{"type": part_type, "text": msg.content or ""}],
    }


def list_envelope(items: list[dict], *, has_more: bool = False) -> dict:
    return {
        "object": "list",
        "data": items,
        "first_id": items[0]["id"] if items else None,
        "last_id": items[-1]["id"] if items else None,
        "has_more": has_more,
    }
