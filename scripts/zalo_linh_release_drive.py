"""Owner-authorized publisher for private Google Drive Zalo Linh artifacts.

This script runs only in a protected GitHub Actions environment with scoped
Drive credentials and a matching Ed25519 key held in GitHub secrets. It cannot
change V7's local trust rules and never handles Zalo credentials or messages.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

from zalo_linh_release import (
    ReleaseError, assert_valid_feed, check_windows_qa, prepare_signed_feed,
    verify_archive, version_parts,
)

ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,150}$")
CANDIDATE_CEILING = 20 * 1024 * 1024


def required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ReleaseError("CONFIGURATION_REQUIRED:" + name)
    return value


def assert_file_id(value: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ReleaseError("DRIVE_FILE_ID_INVALID")
    return value


def client():
    # Intentionally import Google modules only here, not in offline unit tests.
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    info = json.loads(required_env("ZALO_LINH_DRIVE_SERVICE_ACCOUNT_JSON"))
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def read_drive(service, file_id: str, *, max_bytes: int = CANDIDATE_CEILING) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    fid = assert_file_id(file_id)
    metadata = service.files().get(fileId=fid, fields="id,name,size,parents,mimeType,trashed").execute()
    if metadata.get("trashed") or int(metadata.get("size", 0)) > max_bytes:
        raise ReleaseError("DRIVE_FILE_SIZE_OR_TRASH_INVALID")
    output = io.BytesIO()
    downloader = MediaIoBaseDownload(output, service.files().get_media(fileId=fid), chunksize=1048576)
    done = False
    while not done:
        _, done = downloader.next_chunk()
        if output.tell() > max_bytes:
            raise ReleaseError("DRIVE_DOWNLOAD_LIMIT")
    return output.getvalue()


def assert_staging_file(service, file_id: str) -> None:
    staging = assert_file_id(required_env("ZALO_LINH_STAGING_FOLDER_ID"))
    info = service.files().get(fileId=assert_file_id(file_id),
                               fields="id,name,parents,trashed").execute()
    if info.get("trashed") or staging not in info.get("parents", []):
        raise ReleaseError("CANDIDATE_NOT_IN_APPROVED_STAGING")


def validate_input(version: str, expected_sha256: str) -> None:
    version_parts(version)
    if version_parts(version) <= (0, 9, 20):
        raise ReleaseError("MINIMUM_PRODUCTION_VERSION_IS_0_9_21")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ReleaseError("EXPECTED_SHA256_REQUIRED")


def beta_metadata(version: str, sha256: str, size: int) -> dict:
    return {"schema": "zalo-linh.channel-beta.v1", "version": version,
            "sha256": sha256, "size": size, "installable": False,
            "message": "Staging only; never feed this to ZaloLinh.exe"}


def save_file(service, file_id: str, blob: bytes, mime_type: str = "application/json") -> None:
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(blob), mimetype=mime_type, resumable=False)
    service.files().update(fileId=assert_file_id(file_id), media_body=media,
                           fields="id,name,size").execute()


def upload_release(service, source_id: str, version: str, blob: bytes) -> None:
    folder = assert_file_id(required_env("ZALO_LINH_RELEASES_FOLDER_ID"))
    new_name = f"zalo-{version}.zip"
    # Refuse ambiguity or accidental overwrite of a previously released ZIP.
    query = f"'{folder}' in parents and name = '{new_name}' and trashed = false"
    current = service.files().list(q=query, fields="files(id,name),nextPageToken",
                                   page_size=20).execute()
    if current.get("files"):
        raise ReleaseError("RELEASE_FILENAME_ALREADY_EXISTS")
    created = service.files().copy(fileId=assert_file_id(source_id),
                                   body={"name": new_name, "parents": [folder]},
                                   fields="id,name,size,md5Checksum").execute()
    result = read_drive(service, created["id"])
    if len(result) != len(blob) or hashlib.sha256(result).digest() != hashlib.sha256(blob).digest():
        raise ReleaseError("COPIED_RELEASE_BYTES_MISMATCH")


def run(args) -> dict:
    validate_input(args.version, args.sha256)
    svc = client()
    assert_staging_file(svc, args.source_file_id)
    archive = read_drive(svc, args.source_file_id)
    if hashlib.sha256(archive).hexdigest() != args.sha256:
        raise ReleaseError("CANDIDATE_SHA256_MISMATCH")
    payload = verify_archive(archive, args.version)

    if args.channel == "beta":
        # Explicitly NOT signed. This feed cannot be passed to the live updater.
        beta = beta_metadata(args.version, payload["sha256"], payload["size"])
        Path(args.output).write_text(json.dumps(beta, indent=2) + "\n", encoding="utf-8")
        return {"channel": "beta", "qa_only": True, "bytes": payload["size"]}

    assert_staging_file(svc, args.qa_file_id)
    qa_raw = read_drive(svc, args.qa_file_id, max_bytes=50000)
    qa = json.loads(qa_raw)
    check_windows_qa(qa, args.version, payload["sha256"])
    stable_file_id = assert_file_id(required_env("ZALO_LINH_STABLE_FILE_ID"))
    old = json.loads(read_drive(svc, stable_file_id, max_bytes=8192))
    assert_valid_feed(old)
    if version_parts(args.version) <= version_parts(old["version"]):
        raise ReleaseError("STABLE_FEED_NOT_MONOTONIC")
    feed = prepare_signed_feed(archive, args.version,
                               required_env("ZALO_LINH_SIGNING_SEED_B64"))
    output = json.dumps(feed, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    # First create an immutable release path. Leave the signed stable pointer
    # unchanged until this copy has been read back and fully validated.
    upload_release(svc, args.source_file_id, args.version, archive)
    save_file(svc, stable_file_id, output)
    back = json.loads(read_drive(svc, stable_file_id, max_bytes=8192))
    assert_valid_feed(back)
    if back != feed:
        raise ReleaseError("STABLE_FEED_READBACK_FAILED")
    Path(args.output).write_bytes(output)
    return {"channel": "stable", "version": args.version, "sha256": payload["sha256"],
            "size": payload["size"], "signed": True, "drive_published": True}


def main():
    parser = argparse.ArgumentParser(description="Publish validated, signed Zalo Linh releases")
    parser.add_argument("--channel", choices=["beta", "stable"], required=True)
    parser.add_argument("--source-file-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--qa-file-id", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        # Do not echo Drive credentials, signer materials or file contents.
        code = str(error) if isinstance(error, ReleaseError) else type(error).__name__
        print("PUBLISH_REJECTED: " + code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
