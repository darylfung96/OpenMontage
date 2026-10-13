"""Contract tests for the RunningHub open-API client.

No network: every test drives a stub session, so the transport contract
(envelopes, task lifecycle, receipts) is locked without spending coins.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools._runninghub.client import RunningHubClient, RunningHubError, RunningHubTimeout


class _Response:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class _Session:
    """Stub session that replays queued responses and records calls."""

    def __init__(self, *responses: _Response, default: _Response | None = None) -> None:
        self.responses = list(responses)
        self.default = default
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.responses:
            return self.responses.pop(0)
        if self.default is not None:
            return self.default
        raise AssertionError(f"unexpected POST {url}")


def _client(session: _Session) -> RunningHubClient:
    return RunningHubClient(api_key="test-key", base_url="https://rh.test", session=session)


def test_submit_app_sends_bearer_key_and_node_list():
    session = _Session(_Response({"code": 0, "data": {"taskId": "12345"}}))
    task_id = _client(session).submit_app("2103143960360300545", [{"nodeId": "479", "fieldName": "value", "fieldValue": "hi"}])

    assert task_id == "12345"
    call = session.calls[0]
    assert call["url"] == "https://rh.test/task/openapi/ai-app/run"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["json"]["webappId"] == 2103143960360300545
    assert call["json"]["apiKey"] == "test-key"
    assert call["json"]["nodeInfoList"][0]["nodeId"] == "479"


def test_submit_app_raises_on_node_errors_before_any_render():
    tips = json.dumps({"node_errors": {"35": {"errors": [{"message": "value out of range"}]}}})
    session = _Session(_Response({"code": 0, "data": {"taskId": "1", "promptTips": tips}}))

    with pytest.raises(RunningHubError) as excinfo:
        _client(session).submit_app("2106414322893619202", [])

    assert excinfo.value.code == "NODE_ERRORS"
    assert excinfo.value.node_errors


def test_poll_returns_final_payload_and_reads_coin_receipt(monkeypatch):
    monkeypatch.setattr("tools._runninghub.client.time.sleep", lambda _seconds: None)
    session = _Session(
        _Response({"status": "RUNNING"}),
        _Response(
            {
                "status": "SUCCESS",
                "results": [{"url": "https://cdn.test/take.mp4", "outputType": "mp4"}],
                "usage": {"consumeCoins": "74", "taskCostTime": "410"},
            }
        ),
    )
    task = _client(session).poll("task-1", timeout_seconds=30, poll_interval=1.0)

    assert RunningHubClient.result_urls(task) == ["https://cdn.test/take.mp4"]
    receipt = RunningHubClient.receipt(task)
    assert receipt["coins"] == 74.0
    assert receipt["money"] is None
    assert receipt["billing_mode"] == "coins"
    assert receipt["task_cost_seconds"] == 410.0


def test_receipt_reads_wallet_charge_from_nested_data():
    payload = {"data": {"status": "SUCCESS", "usage": {"consumeMoney": "0.014"}}}
    receipt = RunningHubClient.receipt(payload)
    assert receipt["money"] == pytest.approx(0.014)
    assert receipt["coins"] is None
    assert receipt["billing_mode"] == "wallet"


def test_poll_failed_task_reports_code_and_balance_flag(monkeypatch):
    monkeypatch.setattr("tools._runninghub.client.time.sleep", lambda _seconds: None)
    session = _Session(
        _Response({"status": "FAILED", "errorCode": "TASK_FAILED", "errorMessage": "Insufficient balance"})
    )

    with pytest.raises(RunningHubError) as excinfo:
        _client(session).poll("task-2", timeout_seconds=30, poll_interval=1.0)

    error = excinfo.value
    assert error.task_id == "task-2"
    assert error.is_insufficient_balance is True


def test_poll_timeout_carries_task_id_for_recovery(monkeypatch):
    monkeypatch.setattr("tools._runninghub.client.time.sleep", lambda _seconds: None)
    session = _Session(default=_Response({"status": "RUNNING"}))

    with pytest.raises(RunningHubTimeout) as excinfo:
        _client(session).poll("task-3", timeout_seconds=0.01, poll_interval=1.0)

    assert excinfo.value.task_id == "task-3"
    assert isinstance(excinfo.value, TimeoutError)


def test_upload_returns_signed_url():
    session = _Session(_Response({"code": 0, "data": {"download_url": "https://cdn.test/ref.png"}}))
    url = _client(session).upload_bytes(b"bytes", "ref.png", "image/png")

    assert url == "https://cdn.test/ref.png"
    call = session.calls[0]
    assert call["url"] == "https://rh.test/openapi/v2/media/upload/binary"
    assert "file" in call["files"]


def test_upload_without_url_is_an_error():
    session = _Session(_Response({"code": 0, "data": {}}))
    with pytest.raises(RunningHubError) as excinfo:
        _client(session).upload_bytes(b"bytes", "ref.png", "image/png")
    assert excinfo.value.code == "UPLOAD_FAILED"


def test_result_urls_ignores_entries_without_a_url():
    task = {"results": [{"text": "no file"}, {"outputUrl": "https://cdn.test/b.png"}, "junk"]}
    assert RunningHubClient.result_urls(task) == ["https://cdn.test/b.png"]


def test_error_envelope_raises_with_code():
    session = _Session(_Response({"code": 1, "msg": "invalid api key"}))
    with pytest.raises(RunningHubError) as excinfo:
        _client(session).submit_app("1", [])
    assert excinfo.value.code == "1"
    assert "invalid api key" in str(excinfo.value)


def test_http_error_includes_status_and_body():
    session = _Session(_Response("upstream boom", status_code=502))
    with pytest.raises(RunningHubError) as excinfo:
        _client(session).submit_app("1", [])
    assert excinfo.value.http_status == 502


def test_missing_key_reports_configured_false(monkeypatch):
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    monkeypatch.delenv("RUNNINGHUB_PERSONAL_KEY", raising=False)
    client = RunningHubClient()
    assert client.is_configured() is False
    assert "RUNNINGHUB_PERSONAL_KEY" in client.unavailable_reason()


def test_personal_key_wins_over_shared_key(monkeypatch):
    """Coin-first: the personal key beats the shared key whenever both exist."""
    monkeypatch.setenv("RUNNINGHUB_PERSONAL_KEY", "personal-key")
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "shared-key")
    client = RunningHubClient()
    assert client.api_key == "personal-key"
    assert client.key_kind == "personal"
    assert client.bills_coins is True


def test_shared_key_used_when_no_personal_key(monkeypatch):
    monkeypatch.delenv("RUNNINGHUB_PERSONAL_KEY", raising=False)
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "shared-key")
    client = RunningHubClient()
    assert client.api_key == "shared-key"
    assert client.key_kind == "shared"
    assert client.bills_coins is False


def test_explicit_key_argument_overrides_environment(monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_PERSONAL_KEY", "personal-key")
    client = RunningHubClient(api_key="explicit-key")
    assert client.api_key == "explicit-key"
    assert client.key_kind == "explicit"


def test_host_defaults_to_ai_site_and_env_override(monkeypatch):
    monkeypatch.delenv("RUNNINGHUB_API_HOST", raising=False)
    assert RunningHubClient().base_url == "https://www.runninghub.ai"
    monkeypatch.setenv("RUNNINGHUB_API_HOST", "https://www.runninghub.cn/")
    assert RunningHubClient().base_url == "https://www.runninghub.cn"
