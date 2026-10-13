"""Contract tests for the RunningHub Qwen-Image-2.1 image edit provider."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools._runninghub.client import RunningHubClient
from tools.base_tool import ToolStatus
from tools.graphics.runninghub_image import RunningHubImage


def _stub_client(monkeypatch, tmp_path: Path) -> RunningHubClient:
    client = RunningHubClient(api_key="test-key")
    monkeypatch.setattr(
        client, "upload_file", lambda path: f"https://cdn.test/{Path(path).name}"
    )
    return client


def test_registry_discovers_runninghub_image(monkeypatch, isolated_tool_registry):
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    isolated_tool_registry.discover("tools")
    tool = isolated_tool_registry.get("runninghub_image")
    assert tool is not None
    assert tool.capability == "image_generation"
    assert tool.provider == "runninghub"


def test_no_key_marks_tool_unavailable(monkeypatch):
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    monkeypatch.delenv("RUNNINGHUB_PERSONAL_KEY", raising=False)
    assert RunningHubImage().get_status() == ToolStatus.UNAVAILABLE
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    assert RunningHubImage().get_status() == ToolStatus.AVAILABLE


def test_personal_key_alone_is_enough(monkeypatch):
    """Coin-first: the personal key alone must make the tool available."""
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    monkeypatch.setenv("RUNNINGHUB_PERSONAL_KEY", "personal-key")
    assert RunningHubImage().get_status() == ToolStatus.AVAILABLE


def test_node_list_maps_references_into_slots_in_order(tmp_path, monkeypatch):
    client = _stub_client(monkeypatch, tmp_path)
    character = tmp_path / "character.png"
    character.write_bytes(b"image-bytes")

    nodes = RunningHubImage()._build_node_info_list(
        {
            "prompt": "put the jar in her hands",
            "reference_image_path": str(character),
            "reference_image_urls": ["https://cdn.ref/item.png", "https://cdn.ref/extra.png"],
        },
        client,
    )

    assert [node["nodeId"] for node in nodes] == ["479", "470", "477", "475"]
    assert nodes[0]["fieldName"] == "value"
    assert nodes[0]["fieldValue"] == "put the jar in her hands"
    # image1 keeps the character reference; local files are uploaded first.
    assert nodes[1]["fieldValue"] == "https://cdn.test/character.png"
    assert nodes[2]["fieldValue"] == "https://cdn.ref/item.png"
    assert nodes[3]["fieldValue"] == "https://cdn.ref/extra.png"


def test_node_list_requires_a_reference_image():
    with pytest.raises(ValueError, match="at least one reference image"):
        RunningHubImage()._build_node_info_list({"prompt": "just a prompt"}, client=None)


def test_node_list_rejects_more_than_five_references():
    inputs = {
        "prompt": "too many",
        "reference_image_urls": [f"https://cdn.ref/{index}.png" for index in range(6)],
    }
    with pytest.raises(ValueError, match="5 image slots"):
        RunningHubImage()._build_node_info_list(inputs, client=None)


def test_estimate_cost_tracks_measured_wallet_rate():
    tool = RunningHubImage()
    assert tool.estimate_cost({}) == pytest.approx(0.02)
    assert tool.estimate_runtime({}) > 0


def test_dry_run_declares_both_billing_modes():
    planned = RunningHubImage().dry_run({"prompt": "edit"})
    assert planned["paid_api"] is True
    assert "coins" in planned["billing"]
    assert "wallet" in planned["billing"]


def test_execute_reports_wallet_receipt_as_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    reference = tmp_path / "character.png"
    reference.write_bytes(b"image-bytes")

    monkeypatch.setattr(RunningHubClient, "submit_app", lambda self, *args, **kwargs: "task-img")
    monkeypatch.setattr(
        RunningHubClient,
        "poll",
        lambda self, *args, **kwargs: {
            "status": "SUCCESS",
            "results": [{"url": "https://cdn.test/1.png"}, {"url": "https://cdn.test/2.png"}],
            "usage": {"consumeMoney": "0.014"},
        },
    )
    monkeypatch.setattr(
        RunningHubClient, "upload_file", lambda self, path: "https://cdn.test/uploaded.png"
    )

    def fake_download(self, url, dest):
        Path(dest).write_bytes(b"image-bytes")
        return Path(dest)

    monkeypatch.setattr(RunningHubClient, "download", fake_download)

    result = RunningHubImage().execute(
        {
            "prompt": "put the jar in her hands",
            "reference_image_path": str(reference),
            "output_path": str(tmp_path / "out.png"),
        }
    )

    assert result.success is True
    assert result.cost_usd == pytest.approx(0.014)
    assert result.data["coins_consumed"] is None
    assert result.data["billing_mode"] == "wallet"
    assert result.data["outputs_returned"] == 2
    assert len(result.artifacts) == 2


def test_execute_reports_coin_receipt_without_usd_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    reference = tmp_path / "character.png"
    reference.write_bytes(b"image-bytes")

    monkeypatch.setattr(RunningHubClient, "submit_app", lambda self, *args, **kwargs: "task-img")
    monkeypatch.setattr(
        RunningHubClient,
        "poll",
        lambda self, *args, **kwargs: {
            "status": "SUCCESS",
            "results": [{"url": "https://cdn.test/1.png"}],
            "usage": {"consumeCoins": "25"},
        },
    )
    monkeypatch.setattr(
        RunningHubClient, "upload_file", lambda self, path: "https://cdn.test/uploaded.png"
    )

    def fake_download(self, url, dest):
        Path(dest).write_bytes(b"image-bytes")
        return Path(dest)

    monkeypatch.setattr(RunningHubClient, "download", fake_download)

    result = RunningHubImage().execute(
        {
            "prompt": "put the jar in her hands",
            "reference_image_path": str(reference),
            "output_path": str(tmp_path / "out.png"),
        }
    )

    assert result.success is True
    assert result.cost_usd == 0.0
    assert result.data["coins_consumed"] == 25.0
    assert result.data["billing_mode"] == "coins"
