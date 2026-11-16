import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import db, main, ml_adapters, observability


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: True)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def json_logs():
    """Capture the app's log lines as parsed JSON."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(observability._RequestIdFilter())
    handler.setFormatter(observability.JsonFormatter())
    logger = logging.getLogger("app")
    logger.addHandler(handler)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    logger.removeHandler(handler)


def test_request_id_is_generated_and_echoed(client):
    r = client.get("/health")
    assert len(r.headers["x-request-id"]) == 32


def test_safe_incoming_request_id_is_kept(client):
    for incoming in ("trace-123", "Jbc0VjQKoAMEbBQ="):  # ours, API Gateway's
        r = client.get("/health", headers={"X-Request-ID": incoming})
        assert r.headers["x-request-id"] == incoming


def test_unsafe_incoming_request_id_is_replaced(client):
    r = client.get("/health", headers={"X-Request-ID": "bad id\nINJECTED"})
    assert r.headers["x-request-id"] != "bad id\nINJECTED"
    assert "\n" not in r.headers["x-request-id"]


def test_access_log_line_uses_route_template_and_request_id(client, json_logs):
    r = client.get("/api/words/word_001?q=secret-search")
    access = [line for line in json_logs() if line.get("event") == "request"]
    assert access, "no access log line"
    line = access[-1]
    assert line["route"] == "/api/words/{word_id}"
    assert line["status"] == 200
    assert line["request_id"] == r.headers["x-request-id"]
    assert "secret-search" not in json.dumps(json_logs())


def test_learner_text_never_reaches_the_logs(client, json_logs):
    marker = "MARKER-learner-said-this"
    client.post("/api/translate", json={"text": marker})
    client.post(
        "/api/pronunciation/score",
        files={"audio": ("clip.m4a", b"audio", "audio/mp4")},
        data={"target_text": marker},
    )
    assert marker not in json.dumps(json_logs())


def test_ml_request_metric_line(client, json_logs, monkeypatch):
    monkeypatch.setattr(ml_adapters, "_transcribe", None)  # stub
    client.post("/api/transcribe", files={"audio": ("clip.m4a", b"audio", "audio/mp4")})
    client.post("/api/translate", json={"text": "Take your pills."})
    metrics = [line for line in json_logs() if line.get("event") == "ml_request"]
    by_service = {m["service"]: m for m in metrics}
    assert by_service["transcribe"]["status"] == "stub"
    assert by_service["translate"]["status"] == "ok"
    assert all(isinstance(m["latency_ms"], float) for m in metrics)


def test_ml_exception_is_counted(client, json_logs, monkeypatch):
    def boom(audio, language):
        raise ValueError("bad language")

    monkeypatch.setattr(ml_adapters, "_transcribe", boom)
    r = client.post("/api/transcribe", files={"audio": ("clip.m4a", b"a", "audio/mp4")})
    assert r.status_code == 400
    metrics = [line for line in json_logs() if line.get("event") == "ml_request"]
    assert metrics[-1]["status"] == "invalid_argument"


@pytest.mark.parametrize("path, data", [
    ("/api/transcribe", {}),
    ("/api/pronunciation/score", {"target_text": "hello"}),
])
def test_oversized_upload_is_413(client, monkeypatch, path, data):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
    r = client.post(path, files={"audio": ("clip.m4a", b"x" * 11, "audio/mp4")}, data=data)
    assert r.status_code == 413


def test_health_reports_data_source(client):
    body = client.get("/health").json()
    assert body["data_source"] in {"postgres", "dynamodb", "mock"}
