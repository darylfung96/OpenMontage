"""DMAD MiniMax H3 image-to-video through the RunningHub AI App API.

Turns a still into motion with the published DMAD MiniMax H3 app
(``2106414322893619202``), the motion stage of the RunningHub chain: Qwen-Image-2.1
still first, then H3 motion. Frames are the length control the app exposes
(frames / 24 = seconds) and steps default to 8 by standing decision; the app's own
durations are honoured closely but not exactly, so callers trim to their beat grid
in post.

Measured behaviour (paid takes, steps=8): output is 1344x768 landscape, 24 fps,
h264 with its own generated audio, delivered in a MOV container that is patched
to MP4 after download. The output canvas follows the input still, so non-16:9
stills are cover-cropped -- feed a 1344x768 substrate for full framing. The
trained ceiling is 362 frames (~15.1s); longer pieces are chunked into sequential
takes.

Billing follows the key: a personal (membership) key bills RH Coins (roughly
9 fixed + 0.24 per frame measured), a shared key bills the account wallet.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools._runninghub.apps import (
    DMAD_MINIMAX_H3_APP_ID,
    DMAD_MINIMAX_H3_PAGE,
    H3_AUDIO_NODES,
    H3_DEFAULT_FRAMES,
    H3_DEFAULT_STEPS,
    H3_FPS,
    H3_FRAMES_NODE,
    H3_IMAGE_NODES,
    H3_MAX_AUDIOS,
    H3_MAX_FRAMES,
    H3_MAX_IMAGES,
    H3_MODEL_LABEL,
    H3_OUTPUT_SIZE,
    H3_PROMPT_NODE,
    H3_STEPS_NODE,
    H3_SUBSTRATE_NOTE,
    h3_estimated_coins,
    h3_estimated_runtime_seconds,
    h3_estimated_wallet_usd,
)
from tools._runninghub.client import RunningHubClient, RunningHubError, RunningHubTimeout
from tools._runninghub.media import (
    extension_from_url,
    fix_mov_to_mp4,
    image_dimensions,
    looks_like_url,
    numbered_output_path,
)
from tools.base_tool import (
    BaseTool,
    DependencyError,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from tools.video._shared import probe_output


class RunningHubVideo(BaseTool):
    name = "runninghub_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "runninghub"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:RUNNINGHUB_API_KEY"]
    install_instructions = (
        "Set RUNNINGHUB_API_KEY in .env for the RunningHub AI App API. "
        "A personal (membership) key bills RH Coins; a shared key bills the account wallet. "
        f"The DMAD MiniMax H3 app is {DMAD_MINIMAX_H3_PAGE}."
    )
    agent_skills = ["runninghub-chain", "ai-video-gen"]

    capabilities = ["image_to_video", "reference_to_video"]
    supports = {
        "image_to_video": True,
        "reference_to_video": True,
        "reference_image": True,
        "multi_reference": True,
        "native_audio": True,
        "duration_control": True,
        "text_to_video": False,
    }
    best_for = [
        "motion from a Qwen-Image-2.1 still on the RunningHub chain",
        "takes that must carry their own generated audio",
        "coin-billed (personal key) rendering with measured per-take receipts",
    ]
    not_good_for = [
        "text-to-video with no start still (feed the Qwen still stage first)",
        "takes longer than the 362-frame ceiling in a single run",
        "portrait delivery straight from a portrait still (canvas follows the input)",
    ]
    fallback = "minimax_video"
    fallback_tools = ["minimax_video", "kling_official_video", "seedance_video"]

    routes = {
        H3_MODEL_LABEL: {
            "image_to_video": f"runninghub:ai-app/{DMAD_MINIMAX_H3_APP_ID}",
            "reference_to_video": f"runninghub:ai-app/{DMAD_MINIMAX_H3_APP_ID}",
        }
    }

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Motion direction. The input still decides how much motion is possible: "
                    "a still already in the target pose holds the pose, a neutral still moves."
                ),
            },
            "model": {
                "type": "string",
                "enum": [H3_MODEL_LABEL],
                "default": H3_MODEL_LABEL,
                "description": "RunningHub motion app route.",
            },
            "reference_image_url": {
                "type": "string",
                "description": "Start still for the take, as a URL.",
            },
            "reference_image_path": {
                "type": "string",
                "description": "Start still for the take, as a local file (uploaded automatically).",
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Further reference stills (image2-9), as URLs.",
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Further reference stills (image2-9), as local files.",
            },
            "reference_audio_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional audio references (audio1-4), as URLs.",
            },
            "reference_audio_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional audio references (audio1-4), as local files.",
            },
            "frames": {
                "type": "integer",
                "minimum": 1,
                "maximum": H3_MAX_FRAMES,
                "default": H3_DEFAULT_FRAMES,
                "description": (
                    f"Take length in frames at {H3_FPS} fps (the app default of "
                    f"{H3_DEFAULT_FRAMES} is ~5.2s). Always set it explicitly; honoured "
                    "closely but not exactly, so trim in post."
                ),
            },
            "duration_seconds": {
                "type": "number",
                "minimum": 0.04,
                "description": "Convenience alternative to frames; takes precedence and converts at 24 fps.",
            },
            "steps": {
                "type": "integer",
                "minimum": 1,
                "default": H3_DEFAULT_STEPS,
                "description": "Sampler steps (standing decision: 8; the app default is 4).",
            },
            "output_path": {
                "type": "string",
                "description": "Where to save the rendered clip.",
            },
            "timeout_seconds": {"type": "integer", "default": 1800},
            "poll_interval": {"type": "number", "default": 5.0},
            "instance_type": {
                "type": "string",
                "default": "default",
                "description": "RunningHub instance class; leave as default unless the app requires another.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=2000, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["timeout"])
    idempotency_key_fields = [
        "prompt",
        "frames",
        "duration_seconds",
        "steps",
        "reference_image_path",
        "reference_image_url",
        "reference_image_paths",
        "reference_image_urls",
    ]
    side_effects = ["paid remote generation via RunningHub AI App API", "writes video file to output_path"]
    user_visible_verification = ["Watch the take for motion quality, framing, and audio"]

    def get_status(self) -> ToolStatus:
        if not RunningHubClient().is_configured():
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        """Conservative wallet quote; a personal key bills coins instead.

        Shared-key wallet billing tracks GPU runtime at the measured $0.7/h
        rate. A personal key spends coins instead (~9 + 0.24/frame), reported
        in the take receipt.
        """
        frames = self.resolve_frames(inputs)
        return h3_estimated_wallet_usd(frames)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return h3_estimated_runtime_seconds(self.resolve_frames(inputs))

    def dry_run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        result = super().dry_run(inputs)
        frames = self.resolve_frames(inputs)
        result.update(
            {
                "paid_api": True,
                "app_id": DMAD_MINIMAX_H3_APP_ID,
                "app_page": DMAD_MINIMAX_H3_PAGE,
                "frames": frames,
                "duration_seconds": round(frames / H3_FPS, 2),
                "steps": int(inputs.get("steps", H3_DEFAULT_STEPS)),
                "billing": (
                    "Key-dependent: personal key bills RH Coins "
                    f"(~{h3_estimated_coins(frames):g} coins for {frames} frames); "
                    f"shared key bills the wallet (~${h3_estimated_wallet_usd(frames):.4f} for {frames} frames)."
                ),
                "substrate_note": H3_SUBSTRATE_NOTE,
                "cost_estimate_basis": "Measured coin and wallet rates; the take receipt decides the actual charge.",
            }
        )
        return result

    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        info["billing_model"] = "coins (personal key) or wallet (shared key)"
        info["app"] = {"id": DMAD_MINIMAX_H3_APP_ID, "page": DMAD_MINIMAX_H3_PAGE}
        info["exposed_nodes"] = {
            "prompt": list(H3_PROMPT_NODE),
            "images": [list(node) for node in H3_IMAGE_NODES],
            "audios": [list(node) for node in H3_AUDIO_NODES],
            "frames": list(H3_FRAMES_NODE),
            "steps": list(H3_STEPS_NODE),
        }
        info["output"] = {
            "size": list(H3_OUTPUT_SIZE),
            "fps": H3_FPS,
            "max_frames": H3_MAX_FRAMES,
            "native_audio": True,
        }
        info["substrate_note"] = H3_SUBSTRATE_NOTE
        return info

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            self.check_dependencies()
        except DependencyError as exc:
            return ToolResult(success=False, error=str(exc))

        client = RunningHubClient()
        start = time.time()
        warnings: list[str] = []
        try:
            node_list = self._build_node_info_list(inputs, client, warnings)
            task_id = client.submit_app(
                DMAD_MINIMAX_H3_APP_ID,
                node_list,
                instance_type=str(inputs.get("instance_type", "default")),
            )
            task = client.poll(
                task_id,
                timeout_seconds=float(inputs.get("timeout_seconds", 1800)),
                poll_interval=float(inputs.get("poll_interval", 5.0)),
            )
            urls = RunningHubClient.result_urls(task)
            if not urls:
                raise RunningHubError(
                    f"RunningHub H3 task {task_id} succeeded without result files",
                    code="NO_RESULTS",
                    task_id=task_id,
                )
            path = self._download_take(client, urls[0], inputs)
            container_fixed = fix_mov_to_mp4(path)
            receipt = RunningHubClient.receipt(task)
            probed = probe_output(path)
        except (RunningHubError, RunningHubTimeout, TimeoutError, ValueError, FileNotFoundError) as exc:
            data: dict[str, Any] = {"provider": self.provider, "app_id": DMAD_MINIMAX_H3_APP_ID}
            if isinstance(exc, RunningHubError):
                data.update(
                    {
                        "error_code": exc.code,
                        "task_id": exc.task_id,
                        "http_status": exc.http_status,
                        "node_errors": exc.node_errors,
                        "insufficient_balance": exc.is_insufficient_balance,
                    }
                )
            elif isinstance(exc, RunningHubTimeout):
                data["task_id"] = exc.task_id
            return ToolResult(
                success=False,
                data=data,
                error=f"RunningHub H3 video generation failed: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return ToolResult(
                success=False,
                data={"provider": self.provider, "app_id": DMAD_MINIMAX_H3_APP_ID},
                error=f"RunningHub H3 video generation failed: {exc}",
            )

        frames = self.resolve_frames(inputs)
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": H3_MODEL_LABEL,
                "app_id": DMAD_MINIMAX_H3_APP_ID,
                "task_id": task_id,
                "prompt": inputs["prompt"],
                "prompt_used": inputs["prompt"],
                "remote_urls": urls,
                "output": str(path),
                "output_path": str(path),
                "video_paths": [str(path)],
                "format": "mp4",
                "frames_requested": frames,
                "duration_seconds_requested": round(frames / H3_FPS, 2),
                "steps": int(inputs.get("steps", H3_DEFAULT_STEPS)),
                "native_audio": True,
                "container_fixed_from_mov": container_fixed,
                "coins_consumed": receipt["coins"],
                "money_consumed": receipt["money"],
                "billing_mode": receipt["billing_mode"],
                "receipt": receipt,
                "warnings": warnings,
                "substrate_note": H3_SUBSTRATE_NOTE,
                "cost_estimate_confidence": "medium",
                "cost_estimate_basis": "Measured coin and wallet rates; reconciled from the task receipt.",
                **probed,
            },
            artifacts=[str(path)],
            cost_usd=receipt["money"] if receipt["money"] is not None else 0.0,
            duration_seconds=round(time.time() - start, 2),
            model=H3_MODEL_LABEL,
        )

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def resolve_frames(self, inputs: dict[str, Any]) -> int:
        """Resolve take length: ``duration_seconds`` wins, then ``frames``, then the app default."""
        frames_value = inputs.get("frames")
        duration = inputs.get("duration_seconds")
        if duration is not None:
            frames_value = int(round(float(duration) * H3_FPS))
        if frames_value is None:
            frames_value = H3_DEFAULT_FRAMES
        frames = int(frames_value)
        if frames < 1:
            raise ValueError(f"frames must be at least 1, got {frames}")
        if frames > H3_MAX_FRAMES:
            raise ValueError(
                f"{frames} frames exceeds the app's trained ceiling of {H3_MAX_FRAMES} "
                f"frames ({H3_MAX_FRAMES / H3_FPS:.1f}s at {H3_FPS} fps); "
                "split the piece into sequential takes and assemble afterwards"
            )
        return frames

    def _build_node_info_list(
        self, inputs: dict[str, Any], client: RunningHubClient, warnings: list[str]
    ) -> list[dict[str, Any]]:
        prompt = str(inputs.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")

        images = self._reference_values(inputs, "image")
        if not images:
            raise ValueError(
                "The DMAD MiniMax H3 app animates a start still: pass reference_image_path or "
                "reference_image_url (run the Qwen-Image-2.1 still stage first for text-to-video work)."
            )
        if len(images) > H3_MAX_IMAGES:
            raise ValueError(
                f"The H3 app exposes {H3_MAX_IMAGES} image slots, got {len(images)} references"
            )
        audios = self._reference_values(inputs, "audio")
        if len(audios) > H3_MAX_AUDIOS:
            raise ValueError(
                f"The H3 app exposes {H3_MAX_AUDIOS} audio slots, got {len(audios)} references"
            )

        warnings.extend(self._substrate_warnings(images))
        frames = self.resolve_frames(inputs)
        steps = int(inputs.get("steps", H3_DEFAULT_STEPS))
        if steps < 1:
            raise ValueError(f"steps must be at least 1, got {steps}")

        node_list: list[dict[str, Any]] = [
            {
                "nodeId": H3_PROMPT_NODE[0],
                "fieldName": H3_PROMPT_NODE[1],
                "fieldValue": prompt,
            },
            {
                "nodeId": H3_FRAMES_NODE[0],
                "fieldName": H3_FRAMES_NODE[1],
                "fieldValue": str(frames),
            },
            {
                "nodeId": H3_STEPS_NODE[0],
                "fieldName": H3_STEPS_NODE[1],
                "fieldValue": str(steps),
            },
        ]
        for (node_id, field_name), reference in zip(H3_IMAGE_NODES, images):
            node_list.append(
                {
                    "nodeId": node_id,
                    "fieldName": field_name,
                    "fieldValue": self._resolve_reference(client, reference),
                }
            )
        for (node_id, field_name), reference in zip(H3_AUDIO_NODES, audios):
            node_list.append(
                {
                    "nodeId": node_id,
                    "fieldName": field_name,
                    "fieldValue": self._resolve_reference(client, reference),
                }
            )
        return node_list

    @staticmethod
    def _reference_values(inputs: dict[str, Any], kind: str) -> list[str]:
        """References in slot order: singular first, then the plural lists."""
        values: list[str] = []
        for key in (f"reference_{kind}_url", f"reference_{kind}_path"):
            value = inputs.get(key)
            if value:
                values.append(str(value))
        for key in (f"reference_{kind}_urls", f"reference_{kind}_paths"):
            for value in inputs.get(key) or []:
                if value:
                    values.append(str(value))
        return values

    @staticmethod
    def _resolve_reference(client: RunningHubClient, value: str) -> str:
        if looks_like_url(value):
            return value
        return client.upload_file(value)

    @staticmethod
    def _substrate_warnings(images: list[str]) -> list[str]:
        """Warn when a local start still will force the H3 canvas off 16:9.

        Remote URLs are not probed -- downloading a reference just to check its
        aspect ratio would cost more than the warning is worth.
        """
        for value in images:
            if looks_like_url(value):
                continue
            dimensions = image_dimensions(value)
            if dimensions is None:
                return []
            width, height = dimensions
            target_ratio = H3_OUTPUT_SIZE[0] / H3_OUTPUT_SIZE[1]
            if abs((width / height) - target_ratio) > 0.05:
                return [
                    f"Start still is {width}x{height}; the H3 app takes its output canvas from the "
                    f"input, so this take will be cover-cropped toward {H3_OUTPUT_SIZE[0]}x{H3_OUTPUT_SIZE[1]}. "
                    "Feed a 1344x768 substrate for full framing."
                ]
            return []
        return []

    def _download_take(
        self, client: RunningHubClient, url: str, inputs: dict[str, Any]
    ) -> Path:
        base = Path(inputs.get("output_path") or "runninghub_h3.mp4")
        if base.suffix.lower() not in (".mp4", ".mov"):
            base = base.with_suffix(
                f".{extension_from_url(url, 'mp4')}"
            )
        return client.download(url, numbered_output_path(base))
