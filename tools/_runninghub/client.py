"""Thin REST client for the RunningHub open API.

RunningHub reaches every model, workflow, and published AI Application from one
host over one asynchronous task protocol:

1. ``POST /openapi/v2/media/upload/binary`` -- stage a local reference file and
   receive a signed URL to pass as a node field value.
2. Submit the work -- ``POST /task/openapi/ai-app/run`` for a published AI App
   (``webappId``), or ``POST /openapi/v2/run/workflow/{id}`` for a workflow
   template the account owns.
3. ``POST /openapi/v2/query`` -- poll the ``taskId`` until ``SUCCESS`` or
   ``FAILED``, then read the result URLs and the billing receipt from the final
   payload.

Billing follows the API key used on the call, not the account: a personal
(membership) key bills RH Coins, a shared key bills the account wallet. That is
why the client surfaces the receipt instead of assuming either, and why the
provider tools reconcile their reported cost from it.

The default host is the ``.ai`` site, where the production Qwen-Image-2.1 and
DMAD MiniMax H3 apps live. Set ``RUNNINGHUB_API_HOST`` to target ``.cn`` or a
gateway instead.
"""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

DEFAULT_BASE_URL = "https://www.runninghub.ai"

_SUCCESS_STATUS = "SUCCESS"
_FAILED_STATUS = "FAILED"

# Balance / credit wording seen when a wallet-billed task cannot be paid for.
_INSUFFICIENT_BALANCE_MARKERS = ("balance", "insufficient", "credit", "余额")

# Key resolution is coin-first. A personal (membership) key bills RH Coins, the
# house default. A shared key bills the account wallet at the shared rate
# (~$0.0002/s), which needs explicit per-batch approval. Reading the shared key
# by default once billed a whole take to the wallet while coins sat unused
# (hypit-first/notes/10-billing.md, 2026-09-22), so the personal key wins
# whenever both are present.
PERSONAL_KEY_ENV = "RUNNINGHUB_PERSONAL_KEY"
SHARED_KEY_ENV = "RUNNINGHUB_API_KEY"


def _resolve_key() -> Optional[str]:
    """Return the key to bill with: personal first, shared as fallback."""
    return os.environ.get(PERSONAL_KEY_ENV) or os.environ.get(SHARED_KEY_ENV)


def _key_kind() -> str:
    """Which key the environment resolved to: ``personal`` or ``shared``."""
    if os.environ.get(PERSONAL_KEY_ENV):
        return "personal"
    if os.environ.get(SHARED_KEY_ENV):
        return "shared"
    return "none"


class RunningHubError(Exception):
    """Raised when RunningHub rejects a call or a task fails.

    ``task_id`` is set when the failure follows a successful submit, so callers
    can surface the task for support or receipt lookup instead of losing it.
    ``node_errors`` carries the per-node validation detail the AI App door
    returns inside ``promptTips`` -- those rejections are free, so a bad node
    map never costs a paid run.
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        task_id: Optional[str] = None,
        http_status: Optional[int] = None,
        node_errors: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.task_id = task_id
        self.http_status = http_status
        self.node_errors = node_errors or {}

    @property
    def is_insufficient_balance(self) -> bool:
        haystack = f"{self.code or ''} {self}".lower()
        return any(marker in haystack for marker in _INSUFFICIENT_BALANCE_MARKERS)


class RunningHubTimeout(TimeoutError):
    """Raised when polling exhausts its budget on a still-running task.

    Subclasses ``TimeoutError`` so existing timeout handling keeps working, and
    carries ``task_id`` so the paid work can be recovered from ``/openapi/v2/query``
    instead of being re-fired.
    """

    def __init__(self, message: str, task_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.task_id = task_id


class RunningHubClient:
    """Client for the RunningHub open API (upload, submit, poll, download)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key or _resolve_key()
        self.key_kind = "explicit" if api_key else _key_kind()
        resolved = (
            base_url
            or os.environ.get("RUNNINGHUB_API_HOST")
            or DEFAULT_BASE_URL
        )
        self.base_url = resolved.rstrip("/")
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def bills_coins(self) -> bool:
        """True when the resolved key is the personal (membership) key.

        Personal key -> RH Coins. Shared key -> account wallet, which needs
        explicit per-batch approval before a paid run.
        """
        return self.key_kind == "personal"

    def unavailable_reason(self) -> str:
        """Human-readable explanation of why the client cannot be used."""
        if self.is_configured():
            return ""
        return (
            "No RunningHub key is set.\n"
            "Set RUNNINGHUB_PERSONAL_KEY (membership key, bills RH Coins - the "
            "house default) or RUNNINGHUB_API_KEY (shared key, bills the account "
            "wallet and needs explicit per-batch approval)."
        )

    def account_status(self) -> dict[str, Any]:
        """Key type and balances. Diagnostic only -- this call is never billed."""
        payload = self._post_json(
            "/uc/openapi/accountStatus", {"apikey": self.api_key}, bearer=False, timeout=20
        )
        return self._payload(payload)

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_file(self, path: Path | str) -> str:
        """Upload a local file and return its signed URL."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Reference file not found: {file_path}")
        media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        return self.upload_bytes(file_path.read_bytes(), file_path.name, media_type)

    def upload_bytes(self, data: bytes, filename: str, media_type: str) -> str:
        """Upload raw bytes and return the signed URL for node use."""
        if not self.is_configured():
            raise RunningHubError(self.unavailable_reason(), code="MISSING_API_KEY")
        payload = self._post_multipart(
            "/openapi/v2/media/upload/binary",
            files={"file": (filename, data, media_type)},
        )
        record = self._payload(payload)
        url = record.get("download_url") or record.get("fileUrl") or record.get("url")
        if not isinstance(url, str) or not url:
            raise RunningHubError(
                "RunningHub upload succeeded but returned no download URL",
                code="UPLOAD_FAILED",
            )
        return url

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit_app(
        self,
        webapp_id: str,
        node_info_list: list[dict[str, Any]],
        instance_type: str = "default",
    ) -> str:
        """Submit a published AI Application task; returns the ``taskId``."""
        payload: dict[str, Any] = {
            "apiKey": self.api_key,
            "webappId": int(webapp_id),
            "nodeInfoList": list(node_info_list),
        }
        if instance_type and instance_type != "default":
            payload["instanceType"] = instance_type
        response = self._post_json("/task/openapi/ai-app/run", payload)
        record = self._payload(response)
        self._raise_on_node_errors(record)
        task_id = record.get("taskId")
        if not task_id:
            raise RunningHubError(
                "RunningHub accepted the AI App submission but returned no taskId",
                code="SUBMIT_FAILED",
            )
        return str(task_id)

    def submit_workflow(
        self,
        workflow_id: str,
        node_info_list: list[dict[str, Any]],
        instance_type: str = "default",
    ) -> str:
        """Submit a Workflow API task (the coin-first door); returns the ``taskId``."""
        payload: dict[str, Any] = {
            "addMetadata": True,
            "nodeInfoList": list(node_info_list),
            "instanceType": instance_type or "default",
            "usePersonalQueue": "false",
        }
        response = self._post_json(f"/openapi/v2/run/workflow/{workflow_id}", payload)
        record = self._payload(response)
        task_id = record.get("taskId") or (record.get("data") or {}).get("taskId")
        if not task_id:
            raise RunningHubError(
                "RunningHub accepted the workflow submission but returned no taskId",
                code="SUBMIT_FAILED",
            )
        return str(task_id)

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    def poll(
        self,
        task_id: str,
        timeout_seconds: float = 1800.0,
        poll_interval: float = 5.0,
        on_poll: Optional[Callable[[str, float], None]] = None,
    ) -> dict[str, Any]:
        """Poll a task until terminal state; returns the final payload.

        ``on_poll(status, elapsed_seconds)`` is called on every non-terminal
        observation so callers can log or emit progress.
        """
        started = time.monotonic()
        deadline = started + max(float(timeout_seconds), 1.0)
        interval = max(float(poll_interval), 1.0)
        while True:
            record = self._payload(
                self._post_json("/openapi/v2/query", {"taskId": task_id})
            )
            status = str(record.get("status") or "").upper()
            elapsed = round(time.monotonic() - started, 1)
            if status == _SUCCESS_STATUS:
                return record
            if status == _FAILED_STATUS:
                code = record.get("errorCode")
                detail = record.get("errorMessage") or "unknown error"
                raise RunningHubError(
                    f"RunningHub task {task_id} failed: [{code}] {detail}",
                    code=str(code) if code is not None else "TASK_FAILED",
                    task_id=task_id,
                )
            if on_poll is not None:
                on_poll(status or "UNKNOWN", elapsed)
            if time.monotonic() >= deadline:
                raise RunningHubTimeout(
                    f"RunningHub task {task_id} still running after "
                    f"{int(timeout_seconds)}s; recover it with taskId {task_id} "
                    "instead of re-firing it.",
                    task_id=task_id,
                )
            time.sleep(interval)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    @staticmethod
    def result_urls(task: dict[str, Any]) -> list[str]:
        """Extract output file URLs from a terminal task payload, in order."""
        record = RunningHubClient._payload(task)
        results = record.get("results")
        if not isinstance(results, list):
            return []
        urls: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("outputUrl")
            if isinstance(url, str) and url:
                urls.append(url)
        return urls

    @staticmethod
    def receipt(task: dict[str, Any]) -> dict[str, Any]:
        """Normalize the billing receipt of a terminal task payload.

        ``coins`` is set when the call billed RH Coins (personal key); ``money``
        is set when it billed the account wallet (shared key). The two are
        mutually exclusive in practice -- a receipt that spent coins reports no
        wallet amount, and vice versa.
        """
        record = RunningHubClient._payload(task)
        usage = record.get("usage")
        usage = usage if isinstance(usage, dict) else {}

        coins = RunningHubClient._first_number(
            record.get("consumeCoins"), usage.get("consumeCoins")
        )
        money = RunningHubClient._first_number(
            record.get("consumeMoney"),
            usage.get("consumeMoney"),
            usage.get("thirdPartyConsumeMoney"),
        )
        cost_time = RunningHubClient._first_number(
            record.get("taskCostTime"), usage.get("taskCostTime")
        )
        return {
            "coins": coins,
            "money": money,
            "money_currency": "account",
            "task_cost_seconds": cost_time,
            "billing_mode": "coins" if coins is not None else ("wallet" if money is not None else "unknown"),
        }

    def download(self, url: str, dest: Path | str) -> Path:
        """Stream a result file to ``dest`` and return the written path."""
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            response = self.session.get(url, stream=True, timeout=600)
        except requests.RequestException as exc:
            raise RunningHubError(f"RunningHub result download failed: {exc}") from exc
        if response.status_code >= 400:
            raise RunningHubError(
                f"RunningHub result download returned HTTP {response.status_code}",
                http_status=response.status_code,
            )
        with open(target, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    handle.write(chunk)
        return target

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _first_number(*values: Any) -> Optional[float]:
        for value in values:
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _payload(response: dict[str, Any]) -> dict[str, Any]:
        """Flatten RunningHub's response envelopes into one lookup dict.

        The AI App door wraps results as ``{"code", "msg", "data": {...}}``
        while the v2 door answers at the top level. Merging both means callers
        read one shape regardless of which door answered.
        """
        if not isinstance(response, dict):
            return {}
        data = response.get("data")
        if isinstance(data, dict):
            return {**response, **data}
        return response

    def _check_envelope(self, response: dict[str, Any], context: str) -> None:
        code = response.get("code")
        if code in (None, 0, "0"):
            return
        message = response.get("msg") or response.get("message") or "unknown error"
        haystack = f"{code} {message}".lower()
        if any(marker in haystack for marker in _INSUFFICIENT_BALANCE_MARKERS):
            raise RunningHubError(
                f"{context} failed: {message} (insufficient balance)",
                code=str(code),
            )
        raise RunningHubError(f"{context} failed: [{code}] {message}", code=str(code))

    @staticmethod
    def _raise_on_node_errors(record: dict[str, Any]) -> None:
        tips = record.get("promptTips")
        if isinstance(tips, str):
            try:
                import json

                tips = json.loads(tips)
            except ValueError:
                return
        if not isinstance(tips, dict):
            return
        node_errors = tips.get("node_errors") or {}
        if node_errors:
            raise RunningHubError(
                "RunningHub rejected the node map before running (no charge); "
                f"node errors: {node_errors}",
                code="NODE_ERRORS",
                node_errors=node_errors,
            )

    def _headers(self, bearer: bool) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if bearer and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        bearer: bool = True,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.post(
                url, json=payload, headers=self._headers(bearer), timeout=timeout
            )
        except requests.RequestException as exc:
            raise RunningHubError(f"RunningHub POST {path} failed: {exc}") from exc
        return self._parse(response, f"POST {path}")

    def _post_multipart(self, path: str, files: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = self.session.post(
                url, files=files, headers=headers, timeout=180
            )
        except requests.RequestException as exc:
            raise RunningHubError(f"RunningHub upload failed: {exc}") from exc
        return self._parse(response, f"POST {path}")

    def _parse(self, response: requests.Response, context: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise RunningHubError(
                f"RunningHub {context} returned HTTP {response.status_code}: "
                f"{response.text[:300]}",
                http_status=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RunningHubError(
                f"RunningHub {context} returned invalid JSON: {response.text[:300]}"
            ) from exc
        if not isinstance(payload, dict):
            raise RunningHubError(f"RunningHub {context} returned an unexpected payload")
        self._check_envelope(payload, f"RunningHub {context}")
        return payload
