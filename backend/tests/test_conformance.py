import pytest

from app.features.agency.repositories import agency as agency_repo
from app.features.agency.services import conformance


@pytest.mark.asyncio
async def test_report_aggregates_checks(db_session, monkeypatch):
    ag = await agency_repo.create(db_session, name="A", status="draft", connection_type="API",
                                  endpoint_url="http://x", expected_payload={"query": "__query__"})

    async def fake_ask(agency, question):
        return {"ok": True, "latency_ms": 120, "answer": "คำตอบภาษาไทย"}

    monkeypatch.setattr(conformance, "_ask", fake_ask)
    report = await conformance.run_conformance(db_session, ag)

    assert report["passed"] is True
    assert {c["name"] for c in report["checks"]} == {
        "responds", "thai_text", "non_empty", "concurrency_3", "garbage_input",
    }


@pytest.mark.asyncio
async def test_failing_check_fails_report(db_session, monkeypatch):
    ag = await agency_repo.create(db_session, name="B", status="draft", connection_type="API", endpoint_url="http://x")

    async def fake_ask(agency, question):
        return {"ok": False, "latency_ms": 0, "answer": "", "error": "ConnectError"}

    monkeypatch.setattr(conformance, "_ask", fake_ask)
    report = await conformance.run_conformance(db_session, ag)
    assert report["passed"] is False
