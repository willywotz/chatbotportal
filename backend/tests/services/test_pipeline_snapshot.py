from app.services.chat.pipeline_snapshot import build_pipeline_snapshot


def test_empty_events_return_empty_list():
    assert build_pipeline_snapshot([], []) == []


def test_folds_steps_agencies_and_errors():
    events = [
        ("step", {"name": "discover", "status": "running"}),
        ("step", {"name": "discover", "status": "done", "ms": 1200}),
        ("agency_start", {"agency_id": "land", "agency_name": "กรมที่ดิน",
                          "query": "q", "section_label": "fees"}),
        ("agency_responded", {"agency_id": "land", "status": "ok", "error_type": None}),
        ("agency_verified", {"agency_id": "land", "status": "passed", "relevance_score": 0.9}),
    ]
    snap = build_pipeline_snapshot(events, [{"agency": "x", "name": "X",
                                             "error_type": "timeout", "message": "m"}])
    assert snap["steps"] == [{"name": "discover", "ms": 1200}]
    assert snap["agencies"] == [{
        "id": "land", "name": "กรมที่ดิน", "status": "passed",
        "error_type": None, "relevance_score": 0.9, "section_label": "fees",
    }]
    assert snap["errors"] == [{"agency": "x", "name": "X",
                               "error_type": "timeout", "message": "m"}]


def test_responded_error_sets_error_type():
    events = [
        ("agency_start", {"agency_id": "a", "agency_name": "A"}),
        ("agency_responded", {"agency_id": "a", "status": "error", "error_type": "http_500"}),
    ]
    snap = build_pipeline_snapshot(events, [])
    assert snap["agencies"][0]["status"] == "error"
    assert snap["agencies"][0]["error_type"] == "http_500"


def test_bare_step_without_status_is_kept_as_done():
    snap = build_pipeline_snapshot([("step", {"name": "summarize"})], [])
    assert snap["steps"] == [{"name": "summarize", "ms": None}]
