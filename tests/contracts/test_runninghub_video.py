"""Contract tests for the RunningHub DMAD MiniMax H3 motion provider."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools._runninghub.apps import (
    H3_DEFAULT_FRAMES,
    H3_DEFAULT_STEPS,
    H3_MAX_FRAMES,
    h3_estimated_coins,
    h3_estimated_wallet_usd,
)
from tools._runninghub.client import RunningHubClient
from tools._runninghub.media import fix_mov_to_mp4, numbered_output_path
from tools.base_tool import ToolStatus
from tools.video.runninghub_video import RunningHubVideo

_MOV_HEADER = (
    b"\x00\x00\x00\x20" + b"ftyp" + b"qt  " + b"\x00\x00\x02\x00" + b"isomiso2avc1mp41"
)


def _stub_client(monkeypatch) -> RunningHubClient:
    client = RunningHubClient(api_key="test-key")
    monkeypatch.setattr(
        client, "upload_file", lambda path: f"https://cdn.test/{Path(path).name}"
    )
    return client


def test_registry_discovers_runninghub_video(monkeypatch, isolated_tool_registry):
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    isolated_tool_registry.discover("tools")
    tool = isolated_tool_registry.get("runninghub_video")
    assert tool is not None
    assert tool.capability == "video_generation"
    assert tool.provider == "runninghub"


def test_no_key_marks_tool_unavailable(monkeypatch):
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    monkeypatch.delenv("RUNNINGHUB_PERSONAL_KEY", raising=False)
    assert RunningHubVideo().get_status() == ToolStatus.UNAVAILABLE
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    assert RunningHubVideo().get_status() == ToolStatus.AVAILABLE


def test_personal_key_alone_is_enough(monkeypatch):
    """Coin-first: the personal key alone must make the tool available."""
    monkeypatch.delenv("RUNNINGHUB_API_KEY", raising=False)
    monkeypatch.setenv("RUNNINGHUB_PERSONAL_KEY", "personal-key")
    assert RunningHubVideo().get_status() == ToolStatus.AVAILABLE


def test_node_list_carries_prompt_frames_steps_and_images(tmp_path, monkeypatch):
    client = _stub_client(monkeypatch)
    still = tmp_path / "still.png"
    still.write_bytes(b"image-bytes")
    warnings: list[str] = []

    nodes = RunningHubVideo()._build_node_info_list(
        {
            "prompt": "she lifts the jar and smiles",
            "frames": 264,
            "reference_image_path": str(still),
            "reference_image_urls": ["https://cdn.ref/second.png"],
        },
        client,
        warnings,
    )

    by_node = {node["nodeId"]: node for node in nodes}
    assert [node["nodeId"] for node in nodes] == ["9", "35", "11", "19", "20"]
    assert by_node["9"]["fieldName"] == "text"
    assert by_node["9"]["fieldValue"] == "she lifts the jar and smiles"
    # Frames and steps are always sent explicitly: the app default of 124 frames
    # reads as ~5.2s and its default step count is 4, not the chosen 8.
    assert by_node["35"] == {"nodeId": "35", "fieldName": "value", "fieldValue": "264"}
    assert by_node["11"] == {"nodeId": "11", "fieldName": "steps", "fieldValue": str(H3_DEFAULT_STEPS)}
    assert by_node["19"]["fieldValue"] == "https://cdn.test/still.png"
    assert by_node["20"]["fieldValue"] == "https://cdn.ref/second.png"


def test_node_list_requires_a_start_still():
    with pytest.raises(ValueError, match="animates a start still"):
        RunningHubVideo()._build_node_info_list({"prompt": "just a prompt"}, client=None, warnings=[])


def test_node_list_rejects_more_than_nine_images():
    inputs = {
        "prompt": "too many",
        "reference_image_urls": [f"https://cdn.ref/{index}.png" for index in range(10)],
    }
    with pytest.raises(ValueError, match="9 image slots"):
        RunningHubVideo()._build_node_info_list(inputs, client=None, warnings=[])


def test_resolve_frames_defaults_and_conversion():
    tool = RunningHubVideo()
    assert tool.resolve_frames({}) == H3_DEFAULT_FRAMES
    assert tool.resolve_frames({"frames": 56}) == 56
    # duration_seconds wins over frames and converts at 24 fps.
    assert tool.resolve_frames({"frames": 264, "duration_seconds": 1}) == 24


def test_resolve_frames_rejects_over_the_trained_ceiling():
    tool = RunningHubVideo()
    assert tool.resolve_frames({"frames": H3_MAX_FRAMES}) == H3_MAX_FRAMES
    with pytest.raises(ValueError, match="trained ceiling"):
        tool.resolve_frames({"frames": H3_MAX_FRAMES + 1})
    with pytest.raises(ValueError, match="trained ceiling"):
        tool.resolve_frames({"duration_seconds": 16})


def test_estimate_cost_grows_with_frames_and_matches_wallet_model():
    tool = RunningHubVideo()
    assert tool.estimate_cost({}) == pytest.approx(h3_estimated_wallet_usd(H3_DEFAULT_FRAMES))
    assert tool.estimate_cost({"frames": 56}) < tool.estimate_cost({"frames": 264})
    assert tool.estimate_cost({"frames": 264}) == pytest.approx(h3_estimated_wallet_usd(264))


def test_dry_run_quotes_coins_and_wallet_for_the_take():
    planned = RunningHubVideo().dry_run({"prompt": "motion", "frames": 264})
    assert planned["paid_api"] is True
    assert planned["frames"] == 264
    assert planned["duration_seconds"] == pytest.approx(11.0)
    assert f"{h3_estimated_coins(264):g} coins" in planned["billing"]


def test_substrate_warning_fires_for_off_ratio_stills(tmp_path):
    portrait = tmp_path / "portrait.png"
    Image.new("RGB", (832, 1120)).save(portrait)
    warnings = RunningHubVideo._substrate_warnings([str(portrait)])
    assert warnings and "cover-cropped" in warnings[0]

    landscape = tmp_path / "landscape.png"
    Image.new("RGB", (1344, 768)).save(landscape)
    assert RunningHubVideo._substrate_warnings([str(landscape)]) == []
    # Remote URLs are never probed for dimensions.
    assert RunningHubVideo._substrate_warnings(["https://cdn.ref/still.png"]) == []


def test_fix_mov_to_mp4_rewrites_only_quicktime_headers(tmp_path):
    mov = tmp_path / "take.mp4"
    mov.write_bytes(_MOV_HEADER)
    assert fix_mov_to_mp4(mov) is True
    patched = mov.read_bytes()
    assert patched[4:8] == b"ftyp"
    assert patched[8:12] == b"isom"
    # Idempotent: an already-standard header is left alone.
    assert fix_mov_to_mp4(mov) is False

    plain = tmp_path / "plain.mp4"
    plain.write_bytes(b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2")
    assert fix_mov_to_mp4(plain) is False


def test_numbered_output_path_never_overwrites(tmp_path):
    first = tmp_path / "take.mp4"
    assert numbered_output_path(first) == first
    first.write_bytes(b"x")
    assert numbered_output_path(first).name == "take_2.mp4"


def test_execute_fixes_container_and_reports_coin_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "test-key")
    still = tmp_path / "still.png"
    Image.new("RGB", (1344, 768)).save(still)

    monkeypatch.setattr(RunningHubClient, "submit_app", lambda self, *args, **kwargs: "task-vid")
    monkeypatch.setattr(
        RunningHubClient,
        "poll",
        lambda self, *args, **kwargs: {
            "status": "SUCCESS",
            "results": [{"url": "https://cdn.test/take.mov"}],
            "usage": {"consumeCoins": "67", "taskCostTime": "372"},
        },
    )
    monkeypatch.setattr(
        RunningHubClient, "upload_file", lambda self, path: "https://cdn.test/uploaded.png"
    )

    def fake_download(self, url, dest):
        Path(dest).write_bytes(_MOV_HEADER)
        return Path(dest)

    monkeypatch.setattr(RunningHubClient, "download", fake_download)

    result = RunningHubVideo().execute(
        {
            "prompt": "she lifts the jar and smiles",
            "reference_image_path": str(still),
            "frames": 264,
            "output_path": str(tmp_path / "take.mp4"),
        }
    )

    assert result.success is True
    assert result.cost_usd == 0.0
    assert result.data["coins_consumed"] == 67.0
    assert result.data["billing_mode"] == "coins"
    assert result.data["container_fixed_from_mov"] is True
    assert result.data["frames_requested"] == 264
    assert result.data["duration_seconds_requested"] == pytest.approx(11.0)
    assert result.data["warnings"] == []
    assert result.artifacts == [str(tmp_path / "take.mp4")]
    assert (tmp_path / "take.mp4").read_bytes()[8:12] == b"isom"
