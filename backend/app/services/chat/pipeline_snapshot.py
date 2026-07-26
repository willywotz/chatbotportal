"""Fold streamed pipeline events into a persistable snapshot.

Mirrors the frontend reducer (useChatStream / chatHelpers): the terminal state
of the pipeline steps and per-agency statuses, stored on Message.agent_steps so
history can show how an answer was produced. Pure — no I/O, no ORM.
"""


def build_pipeline_snapshot(events: list[tuple[str, dict]], errors: list) -> dict | list:
    """Return the snapshot dict, or [] when no pipeline data was captured."""
    step_order: list[str] = []
    step_ms: dict[str, int | None] = {}
    for name, data in events:
        if name != "step":
            continue
        step_name = data.get("name")
        if step_name is None:
            continue
        if step_name not in step_ms:
            step_order.append(step_name)
        if data.get("status") != "running":
            step_ms[step_name] = data.get("ms")
        else:
            step_ms.setdefault(step_name, None)

    agencies: dict[str, dict] = {}
    for name, data in events:
        if name not in ("agency_start", "agency_responded", "agency_verified"):
            continue
        agency_id = data.get("agency_id")
        if agency_id is None:
            continue
        entry = agencies.setdefault(agency_id, {
            "id": agency_id, "name": data.get("agency_name"), "status": "running",
            "error_type": None, "relevance_score": None,
            "section_label": data.get("section_label"),
        })
        if data.get("agency_name"):
            entry["name"] = data["agency_name"]
        if name == "agency_responded":
            entry["status"] = "ok" if data.get("status") == "ok" else "error"
            entry["error_type"] = data.get("error_type")
        elif name == "agency_verified":
            entry["status"] = data.get("status")
            entry["relevance_score"] = data.get("relevance_score")

    steps = [{"name": n, "ms": step_ms[n]} for n in step_order]
    agency_list = list(agencies.values())
    error_list = list(errors or [])
    if not steps and not agency_list and not error_list:
        return []
    return {"steps": steps, "agencies": agency_list, "errors": error_list}
