"""Facebook Page Reels publisher using the official Graph API v25.0.

The adapter intentionally does not own or persist a Page access token.  A
callable (normally backed by the operating-system secret store) supplies the
token for each public operation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from .base import (
    PublishCheckpoint,
    PublishCheckpointCallback,
    PublishRequest,
    PublishResult,
    PublisherError,
)


TokenProvider = Callable[[], str]
Sleep = Callable[[float], None]
Clock = Callable[[], datetime]


class FacebookPublisher:
    """Publish and verify Reels on one Facebook Page.

    A successful ``finish`` call is never blindly repeated.  If its HTTP
    outcome is ambiguous, the adapter first reconciles the video status and
    otherwise raises ``PublisherError(unknown_outcome=True)``.  This allows the
    job runner to pause for reconciliation instead of creating a duplicate.
    """

    platform = "facebook"
    graph_version = "v25.0"
    graph_base_url = f"https://graph.facebook.com/{graph_version}"

    _MIN_SCHEDULE_LEAD = timedelta(minutes=10)
    _MAX_SCHEDULE_LEAD = timedelta(days=180)
    _SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(
        self,
        *,
        page_id: str,
        token_provider: TokenProvider,
        client: httpx.Client | None = None,
        timeout: httpx.Timeout | float = 60.0,
        poll_interval_seconds: float = 2.0,
        max_status_polls: int = 30,
        max_upload_attempts: int = 3,
        sleep: Sleep = time.sleep,
        clock: Clock | None = None,
        checkpoint_callback: PublishCheckpointCallback | None = None,
    ) -> None:
        page_id = str(page_id)
        if not page_id.isdigit():
            raise ValueError("page_id must be a numeric Facebook Page ID")
        if not callable(token_provider):
            raise TypeError("token_provider must be callable")
        if checkpoint_callback is not None and not callable(checkpoint_callback):
            raise TypeError("checkpoint_callback must be callable")
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be non-negative")
        if max_status_polls < 1:
            raise ValueError("max_status_polls must be at least 1")
        if max_upload_attempts < 1:
            raise ValueError("max_upload_attempts must be at least 1")

        self.page_id = page_id
        self._token_provider = token_provider
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._poll_interval_seconds = poll_interval_seconds
        self._max_status_polls = max_status_polls
        self._max_upload_attempts = max_upload_attempts
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._checkpoint_callback = checkpoint_callback

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FacebookPublisher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def publish(self, request: PublishRequest) -> PublishResult:
        """Upload, publish/schedule, and verify one approved Page Reel."""

        video_path, file_size, scheduled_at = self._validate_request(request)
        token = self._get_token()

        video_id, upload_url = self._start_upload(token)
        try:
            return self._publish_started(
                request=request,
                token=token,
                video_id=video_id,
                upload_url=upload_url,
                video_path=video_path,
                file_size=file_size,
                scheduled_at=scheduled_at,
            )
        except PublisherError as exc:
            # Once Meta allocates a video_id, every failure must carry it so the
            # orchestrator can reconcile the existing remote upload rather than
            # start a second one.
            exc.metadata.setdefault("video_id", video_id)
            raise
        except Exception as exc:
            # Unexpected failures are also converted to the structured contract.
            # Conservatively require reconciliation because the failure point may
            # have been after Meta accepted the finish mutation.
            raise PublisherError(
                "facebook.unexpected_error",
                "Unexpected Facebook failure; verify video_id before retrying.",
                retryable=False,
                unknown_outcome=True,
                metadata={
                    "video_id": video_id,
                    "required_action": "verify_before_retry",
                },
            ) from exc

    def _publish_started(
        self,
        *,
        request: PublishRequest,
        token: str,
        video_id: str,
        upload_url: str,
        video_path: Path,
        file_size: int,
        scheduled_at: datetime | None,
    ) -> PublishResult:
        self._emit_checkpoint(request=request, video_id=video_id)
        self._validate_upload_url(upload_url)
        self._upload_video(
            token=token,
            video_id=video_id,
            upload_url=upload_url,
            video_path=video_path,
            file_size=file_size,
        )

        finish_payload, reconciled_status = self._finish(
            token=token,
            video_id=video_id,
            caption=request.caption,
            scheduled_at=scheduled_at,
            options=request.options,
        )

        scheduled = scheduled_at is not None
        verification_error: Mapping[str, Any] | None = None
        status = reconciled_status
        if status is None:
            status, verification_error = self._poll_status(
                token=token,
                video_id=video_id,
                scheduled=scheduled,
            )

        phase_error = self._find_phase_error(status)
        if phase_error is not None:
            raise PublisherError(
                "facebook.processing_failed",
                self._phase_error_message(phase_error),
                retryable=False,
                metadata={"video_id": video_id, "status": status},
            )

        if scheduled:
            state = "scheduled"
            message = "Facebook accepted the Reel schedule."
        elif self._is_published(status):
            state = "published"
            message = "Facebook published and verified the Reel."
        else:
            state = "processing"
            message = (
                "Facebook accepted the Reel, but publishing is still being "
                "processed; reconcile by video_id before any retry."
            )

        post_id_value = finish_payload.get("post_id")
        post_id = str(post_id_value) if post_id_value is not None else None
        remote_id = post_id or video_id
        permalink_url: str | None = None
        permalink_error: Mapping[str, Any] | None = None
        if state == "published" and post_id:
            permalink_url, permalink_error = self._get_permalink(token, post_id)

        metadata: dict[str, Any] = {
            "video_id": video_id,
            "post_id": post_id,
            "status": status,
            "finish_response": finish_payload,
        }
        if scheduled_at is not None:
            metadata["scheduled_at_utc"] = scheduled_at.isoformat()
        if reconciled_status is not None:
            metadata["reconciled_after_ambiguous_finish"] = True
        if verification_error is not None:
            metadata["verification_error"] = dict(verification_error)
        if permalink_error is not None:
            metadata["permalink_error"] = dict(permalink_error)

        return PublishResult(
            state=state,
            remote_id=remote_id,
            permalink_url=permalink_url,
            metadata=metadata,
            message=message,
        )

    def verify(self, video_id: str, *, post_id: str | None = None) -> PublishResult:
        """Reconcile a previously accepted/ambiguous Reel without mutating it."""

        video_id = self._validate_remote_id(video_id, "video_id")
        if post_id is not None:
            post_id = self._validate_remote_id(post_id, "post_id")
        token = self._get_token()
        status = self._get_status(token, video_id)
        phase_error = self._find_phase_error(status)
        if phase_error is not None:
            raise PublisherError(
                "facebook.processing_failed",
                self._phase_error_message(phase_error),
                retryable=False,
                metadata={"video_id": video_id, "status": status},
            )

        state = "published" if self._is_published(status) else "processing"
        permalink_url: str | None = None
        permalink_error: Mapping[str, Any] | None = None
        if state == "published" and post_id:
            permalink_url, permalink_error = self._get_permalink(token, post_id)

        metadata: dict[str, Any] = {
            "video_id": video_id,
            "post_id": post_id,
            "status": status,
        }
        if permalink_error is not None:
            metadata["permalink_error"] = dict(permalink_error)
        return PublishResult(
            state=state,
            remote_id=post_id or video_id,
            permalink_url=permalink_url,
            metadata=metadata,
            message=(
                "Facebook reports that the Reel is published."
                if state == "published"
                else "Facebook is still processing the Reel."
            ),
        )

    def verify_page_access(self) -> Mapping[str, Any]:
        """Read the configured Page identity without creating remote content."""

        token = self._get_token()
        try:
            response = self._client.get(
                f"{self.graph_base_url}/{quote(self.page_id, safe='')}",
                params={"fields": "id,name"},
                headers=self._auth_headers(token),
            )
        except httpx.RequestError as exc:
            raise PublisherError(
                "facebook.page_check_network",
                "Could not verify the Facebook Page because the network failed.",
                retryable=True,
            ) from exc
        payload = self._decode_response(response, token=token, stage="page_identity")
        remote_page_id = str(payload.get("id") or "")
        if remote_page_id != self.page_id:
            raise PublisherError(
                "facebook.page_identity_mismatch",
                "The stored token does not resolve to the configured Facebook Page.",
                retryable=False,
                metadata={"expected_page_id": self.page_id, "actual_page_id": remote_page_id},
            )
        return {"id": remote_page_id, "name": str(payload.get("name") or "")}

    def _validate_request(
        self, request: PublishRequest
    ) -> tuple[Path, int, datetime | None]:
        video_path = Path(request.video_path)
        if not video_path.is_file():
            raise PublisherError(
                "facebook.video_not_found",
                f"Video file does not exist: {video_path}",
            )
        try:
            file_size = video_path.stat().st_size
        except OSError as exc:
            raise PublisherError(
                "facebook.video_unreadable",
                f"Cannot inspect video file: {exc}",
            ) from exc
        if file_size <= 0:
            raise PublisherError(
                "facebook.empty_video", "Facebook cannot upload an empty video file."
            )
        expected_sha256 = str(request.options.get("video_sha256") or "").strip().lower()
        if expected_sha256:
            if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
                raise PublisherError(
                    "facebook.invalid_video_hash",
                    "Expected video SHA-256 is invalid.",
                    retryable=False,
                )
            digest = hashlib.sha256()
            try:
                with video_path.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        digest.update(chunk)
            except OSError as exc:
                raise PublisherError(
                    "facebook.video_unreadable",
                    f"Cannot verify the video before upload: {exc}",
                    retryable=False,
                ) from exc
            if digest.hexdigest() != expected_sha256:
                raise PublisherError(
                    "facebook.video_changed",
                    "Video content changed after approval; Facebook upload was stopped.",
                    retryable=False,
                )

        scheduled_at = request.scheduled_at_utc
        if scheduled_at is not None:
            if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
                raise PublisherError(
                    "facebook.invalid_schedule",
                    "scheduled_at_utc must be timezone-aware.",
                )
            scheduled_at = scheduled_at.astimezone(timezone.utc)
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise RuntimeError(
                    "FacebookPublisher clock must return an aware datetime"
                )
            now = now.astimezone(timezone.utc)
            lead = scheduled_at - now
            if lead < self._MIN_SCHEDULE_LEAD:
                raise PublisherError(
                    "facebook.invalid_schedule",
                    "Facebook schedules must be at least 10 minutes in the future.",
                )
            if lead > self._MAX_SCHEDULE_LEAD:
                raise PublisherError(
                    "facebook.invalid_schedule",
                    "Facebook schedules cannot be more than 180 days in the future.",
                )
        return video_path, file_size, scheduled_at

    def _get_token(self) -> str:
        try:
            token = self._token_provider()
        except Exception as exc:  # secret stores expose provider-specific errors
            raise PublisherError(
                "facebook.secret_unavailable",
                "Facebook Page access token is unavailable.",
                retryable=False,
            ) from exc
        if not isinstance(token, str) or not token.strip():
            raise PublisherError(
                "facebook.secret_unavailable",
                "Facebook Page access token is missing.",
                retryable=False,
            )
        return token.strip()

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _emit_checkpoint(self, *, request: PublishRequest, video_id: str) -> None:
        """Persist Meta's remote ID before sending any video bytes."""

        callback = self._checkpoint_callback
        if callback is None:
            return
        checkpoint = PublishCheckpoint(
            platform=self.platform,
            post_id=request.post_id,
            stage="upload_initialized",
            remote_id=video_id,
            metadata={"video_id": video_id, "page_id": self.page_id},
        )
        try:
            callback(checkpoint)
        except Exception as exc:
            raise PublisherError(
                "facebook.checkpoint_failed",
                "Could not save Facebook video_id; upload was stopped safely.",
                retryable=False,
                unknown_outcome=False,
                metadata={
                    "video_id": video_id,
                    "stage": "checkpoint",
                    "required_action": "save_checkpoint_before_resume",
                },
            ) from exc

    def _start_upload(self, token: str) -> tuple[str, str]:
        url = f"{self.graph_base_url}/{self.page_id}/video_reels"
        try:
            response = self._client.post(
                url,
                headers=self._auth_headers(token),
                data={"upload_phase": "start"},
            )
        except httpx.RequestError as exc:
            raise PublisherError(
                "facebook.transport_error",
                "Could not start the Facebook upload session.",
                retryable=True,
                metadata={"stage": "start"},
            ) from exc
        payload = self._decode_response(response, token=token, stage="start")
        video_id_value = payload.get("video_id")
        upload_url_value = payload.get("upload_url")
        if video_id_value is None or not isinstance(upload_url_value, str):
            raise PublisherError(
                "facebook.invalid_response",
                "Facebook did not return video_id and upload_url.",
                retryable=True,
                metadata={"stage": "start", "http_status": response.status_code},
            )
        video_id = self._validate_remote_id(str(video_id_value), "video_id")
        return video_id, upload_url_value

    def _upload_video(
        self,
        *,
        token: str,
        video_id: str,
        upload_url: str,
        video_path: Path,
        file_size: int,
    ) -> None:
        offset = 0
        last_transport_error: Exception | None = None

        for attempt in range(1, self._max_upload_attempts + 1):
            try:
                with video_path.open("rb") as video_file:
                    video_file.seek(offset)
                    response = self._client.post(
                        upload_url,
                        headers={
                            "Authorization": f"OAuth {token}",
                            "Content-Type": "application/octet-stream",
                            "offset": str(offset),
                            "file_size": str(file_size),
                        },
                        content=video_file,
                    )
            except OSError as exc:
                raise PublisherError(
                    "facebook.video_unreadable",
                    f"Cannot read video file: {exc}",
                    metadata={"video_id": video_id},
                ) from exc
            except httpx.RequestError as exc:
                last_transport_error = exc
                status = self._safe_get_status(token, video_id)
                if status is not None and self._is_upload_complete(status):
                    return
                offset = self._resume_offset(
                    status, current=offset, file_size=file_size
                )
                if attempt < self._max_upload_attempts:
                    self._sleep(self._poll_interval_seconds)
                    continue
                break

            if response.status_code >= 500 or response.status_code == 408:
                status = self._safe_get_status(token, video_id)
                if status is not None and self._is_upload_complete(status):
                    return
                offset = self._resume_offset(
                    status, current=offset, file_size=file_size
                )
                if attempt < self._max_upload_attempts:
                    self._sleep(self._poll_interval_seconds)
                    continue

            payload = self._decode_response(response, token=token, stage="upload")
            if payload.get("success") is True:
                return
            raise PublisherError(
                "facebook.upload_failed",
                "Facebook did not accept the video bytes.",
                retryable=True,
                metadata={"video_id": video_id, "stage": "upload"},
            )

        raise PublisherError(
            "facebook.transport_error",
            "Facebook upload was interrupted and could not be resumed.",
            retryable=True,
            metadata={"video_id": video_id, "offset": offset, "stage": "upload"},
        ) from last_transport_error

    def _finish(
        self,
        *,
        token: str,
        video_id: str,
        caption: str,
        scheduled_at: datetime | None,
        options: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        url = f"{self.graph_base_url}/{self.page_id}/video_reels"
        data: dict[str, str] = {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "SCHEDULED" if scheduled_at else "PUBLISHED",
            "description": caption,
        }
        if scheduled_at is not None:
            data["scheduled_publish_time"] = str(int(scheduled_at.timestamp()))
        title = options.get("facebook_title", options.get("title"))
        if title is not None:
            if not isinstance(title, str):
                raise PublisherError(
                    "facebook.invalid_option", "Facebook Reel title must be text."
                )
            data["title"] = title

        try:
            response = self._client.post(
                url,
                headers=self._auth_headers(token),
                data=data,
            )
        except httpx.RequestError as exc:
            return self._reconcile_ambiguous_finish(
                token=token,
                video_id=video_id,
                scheduled=scheduled_at is not None,
                cause=exc,
            )

        if response.status_code >= 500 or response.status_code == 408:
            return self._reconcile_ambiguous_finish(
                token=token,
                video_id=video_id,
                scheduled=scheduled_at is not None,
                http_status=response.status_code,
            )

        payload = self._decode_response(response, token=token, stage="finish")
        if payload.get("success") is not True:
            raise PublisherError(
                "facebook.finish_failed",
                "Facebook did not accept the final publish command.",
                retryable=False,
                metadata={"video_id": video_id, "stage": "finish"},
            )
        return payload, None

    def _reconcile_ambiguous_finish(
        self,
        *,
        token: str,
        video_id: str,
        scheduled: bool,
        cause: Exception | None = None,
        http_status: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        last_status: dict[str, Any] | None = None
        # A short read-only reconciliation window prevents an immediate second
        # finish call while allowing Meta a moment to expose the accepted post.
        for attempt in range(min(3, self._max_status_polls)):
            last_status = self._safe_get_status(token, video_id)
            if not scheduled and self._is_published(last_status):
                return {"success": True}, last_status or {}
            if attempt + 1 < min(3, self._max_status_polls):
                self._sleep(self._poll_interval_seconds)

        metadata: dict[str, Any] = {
            "video_id": video_id,
            "stage": "finish",
            "last_status": last_status,
            "required_action": "verify_before_retry",
        }
        if http_status is not None:
            metadata["http_status"] = http_status
        error = PublisherError(
            "facebook.finish_unknown",
            "Facebook may have accepted the Reel. Verify video_id before retrying.",
            retryable=False,
            unknown_outcome=True,
            metadata=metadata,
        )
        if cause is not None:
            raise error from cause
        raise error

    def _poll_status(
        self, *, token: str, video_id: str, scheduled: bool
    ) -> tuple[dict[str, Any] | None, Mapping[str, Any] | None]:
        attempts = 1 if scheduled else self._max_status_polls
        last_status: dict[str, Any] | None = None
        last_error: Mapping[str, Any] | None = None

        for attempt in range(attempts):
            try:
                last_status = self._get_status(token, video_id)
                last_error = None
            except PublisherError as exc:
                last_error = exc.as_dict()
                if not exc.retryable:
                    break
            else:
                phase_error = self._find_phase_error(last_status)
                if (
                    phase_error is not None
                    or scheduled
                    or self._is_published(last_status)
                ):
                    break
            if attempt + 1 < attempts:
                self._sleep(self._poll_interval_seconds)
        return last_status, last_error

    def _get_status(self, token: str, video_id: str) -> dict[str, Any]:
        video_id = self._validate_remote_id(video_id, "video_id")
        url = f"{self.graph_base_url}/{quote(video_id, safe='')}"
        try:
            response = self._client.get(
                url,
                headers=self._auth_headers(token),
                params={"fields": "status"},
            )
        except httpx.RequestError as exc:
            raise PublisherError(
                "facebook.transport_error",
                "Could not retrieve Facebook video status.",
                retryable=True,
                metadata={"video_id": video_id, "stage": "status"},
            ) from exc
        payload = self._decode_response(response, token=token, stage="status")
        status = payload.get("status")
        if not isinstance(status, Mapping):
            raise PublisherError(
                "facebook.invalid_response",
                "Facebook video status response is missing status.",
                retryable=True,
                metadata={"video_id": video_id, "stage": "status"},
            )
        return dict(status)

    def _safe_get_status(self, token: str, video_id: str) -> dict[str, Any] | None:
        try:
            return self._get_status(token, video_id)
        except PublisherError:
            return None

    def _get_permalink(
        self, token: str, post_id: str
    ) -> tuple[str | None, Mapping[str, Any] | None]:
        post_id = self._validate_remote_id(post_id, "post_id")
        url = f"{self.graph_base_url}/{quote(post_id, safe='')}"
        try:
            response = self._client.get(
                url,
                headers=self._auth_headers(token),
                params={"fields": "is_published,permalink_url,created_time"},
            )
            payload = self._decode_response(response, token=token, stage="permalink")
        except httpx.RequestError:
            return None, {
                "code": "facebook.transport_error",
                "retryable": True,
                "stage": "permalink",
            }
        except PublisherError as exc:
            return None, exc.as_dict()
        permalink = payload.get("permalink_url")
        if permalink is None:
            return None, {
                "code": "facebook.permalink_pending",
                "retryable": True,
                "stage": "permalink",
            }
        if not isinstance(permalink, str):
            return None, {
                "code": "facebook.invalid_response",
                "retryable": True,
                "stage": "permalink",
            }
        return permalink, None

    def _decode_response(
        self, response: httpx.Response, *, token: str, stage: str
    ) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            if response.status_code >= 400:
                raise PublisherError(
                    "facebook.http_error",
                    f"Facebook returned HTTP {response.status_code} during {stage}.",
                    retryable=response.status_code == 429
                    or response.status_code >= 500,
                    metadata={"http_status": response.status_code, "stage": stage},
                ) from exc
            raise PublisherError(
                "facebook.invalid_response",
                f"Facebook returned invalid JSON during {stage}.",
                retryable=True,
                metadata={"http_status": response.status_code, "stage": stage},
            ) from exc

        if not isinstance(payload, Mapping):
            raise PublisherError(
                "facebook.invalid_response",
                f"Facebook returned an unexpected response during {stage}.",
                retryable=response.status_code >= 500,
                metadata={"http_status": response.status_code, "stage": stage},
            )
        payload_dict = dict(payload)
        if response.status_code >= 400 or isinstance(
            payload_dict.get("error"), Mapping
        ):
            raise self._graph_error(response, payload_dict, token=token, stage=stage)
        return payload_dict

    def _graph_error(
        self,
        response: httpx.Response,
        payload: Mapping[str, Any],
        *,
        token: str,
        stage: str,
    ) -> PublisherError:
        raw_error = payload.get("error")
        error = raw_error if isinstance(raw_error, Mapping) else {}
        graph_code = self._as_int(error.get("code"))
        graph_subcode = self._as_int(error.get("error_subcode"))
        is_transient = error.get("is_transient") is True
        message_value = error.get("message")
        message = (
            str(message_value)
            if message_value
            else f"Facebook returned HTTP {response.status_code} during {stage}."
        )
        # A Graph message should not contain a credential, but redact defensively
        # so provider/fixture mistakes never expose it through logs or the UI.
        message = message.replace(token, "[REDACTED]")

        retryable_codes = {1, 2, 4, 17, 32, 341, 613}
        retryable = (
            is_transient
            or graph_code in retryable_codes
            or response.status_code == 429
            or response.status_code >= 500
        )
        if graph_code == 190:
            code = "facebook.auth_required"
            retryable = False
        elif graph_code == 200:
            code = "facebook.permission_denied"
            retryable = False
        elif graph_code == 368:
            code = "facebook.action_blocked"
            retryable = False
        elif graph_code == 613 or response.status_code == 429:
            code = "facebook.rate_limited"
            retryable = True
        elif graph_code == 100 or (
            graph_code is not None and 1_363_000 <= graph_code < 1_364_000
        ):
            code = "facebook.invalid_request"
            retryable = False
        elif graph_code in {6000, 6001}:
            code = "facebook.upload_failed"
        else:
            code = "facebook.api_error"

        return PublisherError(
            code,
            message,
            retryable=retryable,
            metadata={
                "stage": stage,
                "http_status": response.status_code,
                "graph_code": graph_code,
                "graph_subcode": graph_subcode,
                "fbtrace_id": error.get("fbtrace_id"),
            },
        )

    @classmethod
    def _validate_remote_id(cls, value: str, field: str) -> str:
        if not value or cls._SAFE_ID.fullmatch(value) is None:
            raise PublisherError(
                "facebook.invalid_response",
                f"Facebook returned an invalid {field}.",
                retryable=False,
            )
        return value

    @staticmethod
    def _validate_upload_url(upload_url: str) -> None:
        parsed = urlsplit(upload_url)
        if parsed.scheme != "https" or parsed.hostname != "rupload.facebook.com":
            raise PublisherError(
                "facebook.invalid_upload_url",
                "Facebook returned an untrusted upload URL.",
                retryable=False,
            )

    @staticmethod
    def _is_upload_complete(status: Mapping[str, Any] | None) -> bool:
        if not isinstance(status, Mapping):
            return False
        phase = status.get("uploading_phase")
        return (
            isinstance(phase, Mapping)
            and str(phase.get("status", "")).lower() == "complete"
        )

    @staticmethod
    def _resume_offset(
        status: Mapping[str, Any] | None, *, current: int, file_size: int
    ) -> int:
        if not isinstance(status, Mapping):
            return current
        phase = status.get("uploading_phase")
        if not isinstance(phase, Mapping):
            return current
        value = phase.get("bytes_transfered", phase.get("bytes_transferred"))
        try:
            offset = int(value)
        except (TypeError, ValueError):
            return current
        return offset if current <= offset < file_size else current

    @staticmethod
    def _is_published(status: Mapping[str, Any] | None) -> bool:
        if not isinstance(status, Mapping):
            return False
        video_status = str(status.get("video_status", "")).lower()
        publishing = status.get("publishing_phase")
        publishing_status = (
            str(publishing.get("status", "")).lower()
            if isinstance(publishing, Mapping)
            else ""
        )
        return video_status == "published" or publishing_status in {
            "complete",
            "published",
        }

    @staticmethod
    def _find_phase_error(status: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
        if not isinstance(status, Mapping):
            return None
        for phase_name in ("uploading_phase", "processing_phase", "publishing_phase"):
            phase = status.get(phase_name)
            if not isinstance(phase, Mapping):
                continue
            phase_status = str(phase.get("status", "")).lower()
            phase_error = phase.get("error")
            if phase_status in {"error", "failed"} or isinstance(phase_error, Mapping):
                if isinstance(phase_error, Mapping):
                    return {"phase": phase_name, **dict(phase_error)}
                return {"phase": phase_name, "message": f"{phase_name} failed"}
        if str(status.get("video_status", "")).lower() in {"error", "failed"}:
            return {"phase": "video", "message": "Facebook video processing failed"}
        return None

    @staticmethod
    def _phase_error_message(error: Mapping[str, Any]) -> str:
        message = error.get("message")
        return str(message) if message else "Facebook could not process the Reel."

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


__all__ = ["FacebookPublisher", "TokenProvider"]
