"""Qwen-Image-2.1 image editing through the RunningHub AI App API.

Runs the published Qwen-Image-2.1 edit app (``2103143960360300545``) against the
account key. The app is reference-conditioned editing, not text-to-image: image1
is the character reference and image2+ are the items or scenes being worked, so
at least one input image is required. Five image slots and one prompt are
exposed; nothing else is adjustable from the API.

Billing follows the key: a personal (membership) key bills RH Coins (~25 per
take measured), a shared key bills the account wallet (~$0.02 per take
measured). Both the estimate and the receipt are reported, and the receipt --
not the assumption -- decides the reconciled cost.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools._runninghub.apps import (
    QWEN_IMAGE_EDIT_APP_ID,
    QWEN_IMAGE_EDIT_IMAGE_NODES,
    QWEN_IMAGE_EDIT_MAX_IMAGES,
    QWEN_IMAGE_EDIT_MEASURED_COINS,
    QWEN_IMAGE_EDIT_MEASURED_WALLET_USD,
    QWEN_IMAGE_EDIT_PAGE,
    QWEN_IMAGE_EDIT_PROMPT_NODE,
    QWEN_IMAGE_EDIT_RUNTIME_SECONDS,
)
from tools._runninghub.client import RunningHubClient, RunningHubError, RunningHubTimeout
from tools._runninghub.media import (
    extension_from_url,
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


class RunningHubImage(BaseTool):
    name = "runninghub_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "runninghub"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:RUNNINGHUB_API_KEY"]
    install_instructions = (
        "Set RUNNINGHUB_API_KEY in .env for the RunningHub AI App API. "
        "A personal (membership) key bills RH Coins; a shared key bills the account wallet. "
        f"The Qwen-Image-2.1 edit app is {QWEN_IMAGE_EDIT_PAGE}."
    )
    agent_skills = ["runninghub-chain"]

    capabilities = ["generate_image", "image_edit", "precise_edit"]
    supports = {
        "image_edit": True,
        "precise_edit": True,
        "reference_image": True,
        "multi_reference": True,
    }
    best_for = [
        "reference-conditioned stills on the RunningHub Qwen-Image-2.1 chain",
        "character + item compositions where image1 must stay the character reference",
        "the still stage that feeds DMAD MiniMax H3 motion",
    ]
    not_good_for = [
        "text-to-image with no reference image (the app edits, it does not invent)",
        "offline or free generation",
    ]
    fallback = "qwen_image_21"
    fallback_tools = ["qwen_image_21", "kling_official_image", "image_gen"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Edit instruction. The app's default prompt treats image1 as the "
                    "character reference and image2 as the item being presented."
                ),
            },
            "reference_image_url": {
                "type": "string",
                "description": "image1 -- character reference (URL).",
            },
            "reference_image_path": {
                "type": "string",
                "description": "image1 -- character reference (local file; uploaded automatically).",
            },
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "image2-5 in order, as URLs.",
            },
            "reference_image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "image2-5 in order, as local files.",
            },
            "output_path": {
                "type": "string",
                "description": "Where to save the first output (extra outputs get numbered suffixes).",
            },
            "timeout_seconds": {"type": "integer", "default": 600},
            "poll_interval": {"type": "number", "default": 5.0},
            "instance_type": {
                "type": "string",
                "default": "default",
                "description": "RunningHub instance class; leave as default unless the app requires another.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=200, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["timeout"])
    idempotency_key_fields = [
        "prompt",
        "reference_image_path",
        "reference_image_url",
        "reference_image_paths",
        "reference_image_urls",
    ]
    side_effects = ["paid remote generation via RunningHub AI App API", "writes image file(s) to output_path"]
    user_visible_verification = ["Inspect edited image for identity and item fidelity"]

    def get_status(self) -> ToolStatus:
        if not RunningHubClient().is_configured():
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        """Conservative wallet quote; a personal key bills coins instead.

        Measured: ~25 coins per take on a personal key, ~$0.02 per take on a
        shared key. The framework budget speaks USD, so the wallet figure is
        quoted and the receipt decides what was actually spent.
        """
        return QWEN_IMAGE_EDIT_MEASURED_WALLET_USD

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return QWEN_IMAGE_EDIT_RUNTIME_SECONDS

    def dry_run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        result = super().dry_run(inputs)
        result.update(
            {
                "paid_api": True,
                "app_id": QWEN_IMAGE_EDIT_APP_ID,
                "app_page": QWEN_IMAGE_EDIT_PAGE,
                "billing": (
                    "Key-dependent: personal key bills RH Coins "
                    f"(~{QWEN_IMAGE_EDIT_MEASURED_COINS:g} coins/take measured); "
                    f"shared key bills the wallet (~${QWEN_IMAGE_EDIT_MEASURED_WALLET_USD:.2f}/take measured)."
                ),
                "cost_estimate_basis": "Measured wallet rate; the take receipt reports the actual charge.",
            }
        )
        return result

    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        info["billing_model"] = "coins (personal key) or wallet (shared key)"
        info["app"] = {"id": QWEN_IMAGE_EDIT_APP_ID, "page": QWEN_IMAGE_EDIT_PAGE}
        info["exposed_nodes"] = {
            "prompt": list(QWEN_IMAGE_EDIT_PROMPT_NODE),
            "images": [list(node) for node in QWEN_IMAGE_EDIT_IMAGE_NODES],
        }
        return info

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            self.check_dependencies()
        except DependencyError as exc:
            return ToolResult(success=False, error=str(exc))

        client = RunningHubClient()
        start = time.time()
        try:
            node_list = self._build_node_info_list(inputs, client)
            task_id = client.submit_app(
                QWEN_IMAGE_EDIT_APP_ID,
                node_list,
                instance_type=str(inputs.get("instance_type", "default")),
            )
            task = client.poll(
                task_id,
                timeout_seconds=float(inputs.get("timeout_seconds", 600)),
                poll_interval=float(inputs.get("poll_interval", 5.0)),
            )
            urls = RunningHubClient.result_urls(task)
            if not urls:
                raise RunningHubError(
                    f"RunningHub Qwen task {task_id} succeeded without result files",
                    code="NO_RESULTS",
                    task_id=task_id,
                )
            paths = self._download_outputs(client, urls, inputs)
            receipt = RunningHubClient.receipt(task)
        except (RunningHubError, RunningHubTimeout, TimeoutError, ValueError, FileNotFoundError) as exc:
            data: dict[str, Any] = {"provider": self.provider, "app_id": QWEN_IMAGE_EDIT_APP_ID}
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
                error=f"RunningHub Qwen image edit failed: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - provider boundary
            return ToolResult(
                success=False,
                data={"provider": self.provider, "app_id": QWEN_IMAGE_EDIT_APP_ID},
                error=f"RunningHub Qwen image edit failed: {exc}",
            )

        dimensions = image_dimensions(paths[0]) or (None, None)
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": "qwen-image-2.1-edit",
                "app_id": QWEN_IMAGE_EDIT_APP_ID,
                "task_id": task_id,
                "prompt": inputs["prompt"],
                "remote_urls": urls,
                "output": str(paths[0]),
                "output_path": str(paths[0]),
                "image_paths": [str(path) for path in paths],
                "format": paths[0].suffix.lstrip(".").lower() or "png",
                "width": dimensions[0],
                "height": dimensions[1],
                "outputs_returned": len(urls),
                "coins_consumed": receipt["coins"],
                "money_consumed": receipt["money"],
                "billing_mode": receipt["billing_mode"],
                "receipt": receipt,
                "cost_estimate_confidence": "medium",
                "cost_estimate_basis": "Measured per-take rates; reconciled from the task receipt.",
            },
            artifacts=[str(path) for path in paths],
            cost_usd=receipt["money"] if receipt["money"] is not None else 0.0,
            duration_seconds=round(time.time() - start, 2),
            model="qwen-image-2.1-edit",
        )

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def _build_node_info_list(
        self, inputs: dict[str, Any], client: RunningHubClient
    ) -> list[dict[str, Any]]:
        prompt = str(inputs.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")

        references = self._reference_values(inputs)
        if not references:
            raise ValueError(
                "The Qwen-Image-2.1 edit app needs at least one reference image: "
                "pass reference_image_path or reference_image_url (image1 is the character reference)."
            )
        if len(references) > QWEN_IMAGE_EDIT_MAX_IMAGES:
            raise ValueError(
                f"The Qwen-Image-2.1 edit app exposes {QWEN_IMAGE_EDIT_MAX_IMAGES} image slots, "
                f"got {len(references)} references"
            )

        node_list = [
            {
                "nodeId": QWEN_IMAGE_EDIT_PROMPT_NODE[0],
                "fieldName": QWEN_IMAGE_EDIT_PROMPT_NODE[1],
                "fieldValue": prompt,
            }
        ]
        for (node_id, field_name), reference in zip(QWEN_IMAGE_EDIT_IMAGE_NODES, references):
            node_list.append(
                {
                    "nodeId": node_id,
                    "fieldName": field_name,
                    "fieldValue": self._resolve_reference(client, reference),
                }
            )
        return node_list

    @staticmethod
    def _reference_values(inputs: dict[str, Any]) -> list[str]:
        """Image references in slot order: image1 first, then image2-5."""
        values: list[str] = []
        for key in ("reference_image_url", "reference_image_path"):
            value = inputs.get(key)
            if value:
                values.append(str(value))
        for key in ("reference_image_urls", "reference_image_paths"):
            for value in inputs.get(key) or []:
                if value:
                    values.append(str(value))
        return values

    @staticmethod
    def _resolve_reference(client: RunningHubClient, value: str) -> str:
        if looks_like_url(value):
            return value
        return client.upload_file(value)

    def _download_outputs(
        self, client: RunningHubClient, urls: list[str], inputs: dict[str, Any]
    ) -> list[Path]:
        base = Path(inputs.get("output_path") or "runninghub_qwen.png")
        paths: list[Path] = []
        for index, url in enumerate(urls):
            if index == 0:
                target = numbered_output_path(base)
            else:
                extension = extension_from_url(url, base.suffix.lstrip(".") or "png")
                target = numbered_output_path(
                    base.with_name(f"{base.stem}_{index + 1}.{extension}")
                )
            paths.append(client.download(url, target))
        return paths
