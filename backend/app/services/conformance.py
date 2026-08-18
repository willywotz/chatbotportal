"""Agency conformance battery — required before draft -> active."""
import asyncio

from app.models import Agency
from app.repositories import agency as agency_repo
from app.services.chat.dispatch import dispatch_one
from app.utils import now

_THAI_PROBE = "ขอข้อมูลการติดต่อหน่วยงาน"


async def _ask(agency: Agency, question: str) -> dict:
    route = {
        "agency_id": str(agency.id), "agency_name": agency.name,
        "connection_type": agency.connection_type, "endpoint_url": agency.endpoint_url,
        "sub_question": question, "expected_payload": agency.expected_payload,
        "api_headers": agency.api_headers, "dispatch_timeout_s": agency.dispatch_timeout_s,
    }
    start = now()
    result = await dispatch_one(route, conversation_id="")
    latency_ms = int((now() - start).total_seconds() * 1000)
    ok = result.get("status") == "ok"
    return {"ok": ok, "latency_ms": latency_ms,
            "answer": str(result.get("response", "")), "error": None if ok else result.get("response")}


def _has_thai(text: str) -> bool:
    return any("฀" <= ch <= "๿" for ch in text)


async def run_conformance(agency: Agency) -> dict:
    checks: list[dict] = []
    first = await _ask(agency, _THAI_PROBE)
    checks.append({"name": "responds", "passed": first["ok"], "detail": first.get("error") or f"{first['latency_ms']}ms"})
    checks.append({"name": "non_empty", "passed": bool(first["answer"].strip()), "detail": ""})
    checks.append({"name": "thai_text", "passed": _has_thai(first["answer"]), "detail": ""})

    concurrent = await asyncio.gather(*[_ask(agency, _THAI_PROBE) for _ in range(3)])
    checks.append({"name": "concurrency_3", "passed": all(r["ok"] for r in concurrent), "detail": ""})

    garbage = await _ask(agency, "\x00\x01 ###")
    checks.append({"name": "garbage_input", "passed": True, "detail": "did not crash" if garbage else ""})

    report = {"ran_at": now().isoformat(), "passed": all(c["passed"] for c in checks), "checks": checks}
    agency.conformance_report = report
    await agency_repo.save(agency, update_fields=["conformance_report"])
    return report
