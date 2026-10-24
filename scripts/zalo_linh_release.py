"""Zalo Linh signed release: strict ZIP/signature gate for GitHub/Drive publisher.

No private signing key stored in this repo or inside a Zalo application.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

PINNED_PUBLIC_KEY_HEX = "f42050c1a1aac293d631bd5024aebb323682b4ab809ab151370ca7eab24ce602"
DOMAIN = "ZALO-LINH-SIGNED-UPDATE-V1"
APP_FILE = re.compile(r"^(VERSION\.txt|app/[A-Za-z_][A-Za-z0-9_-]{0,110}\.(?:py|js))$")
VERSION = re.compile(r"^(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})$")
SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_ARCHIVE = 20 * 1024 * 1024
MAX_UNCOMPRESSED = 40 * 1024 * 1024
MAX_ITEMS = 100


class ReleaseError(ValueError):
    pass


def version_parts(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ReleaseError("INVALID_VERSION")
    return tuple(map(int, value.split(".")))


def canonical(feed: dict) -> bytes:
    if set(feed) != {"version", "url", "size", "sha256", "signature"}:
        raise ReleaseError("FEED_FIELDS_MISMATCH")
    return (f"{DOMAIN}\n{feed['version']}\n{feed['sha256']}\n"
            f"{feed['size']}\n{feed['url']}\n").encode("utf-8")


def release_url(version: str) -> str:
    version_parts(version)
    return f"gdrive://ZaloLinhUpdates/releases/zalo-{version}.zip"


def assert_valid_feed(feed: dict, public_key_hex: str = PINNED_PUBLIC_KEY_HEX) -> None:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        if not isinstance(feed, dict) or set(feed) != {"version", "url", "size", "sha256", "signature"}:
            raise ReleaseError("FEED_FIELDS_MISMATCH")
        version_parts(feed["version"])
        if feed["url"] != release_url(feed["version"]):
            raise ReleaseError("FEED_URL_UNTRUSTED")
        if type(feed["size"]) is not int or not 100 <= feed["size"] <= MAX_ARCHIVE:
            raise ReleaseError("FEED_SIZE_INVALID")
        if not isinstance(feed["sha256"], str) or not SHA.fullmatch(feed["sha256"]):
            raise ReleaseError("FEED_SHA_INVALID")
        sig = bytes.fromhex(feed["signature"])
        if len(sig) != 64:
            raise ReleaseError("FEED_SIGNATURE_LENGTH")
        pub = bytes.fromhex(public_key_hex)
        if len(pub) != 32:
            raise ReleaseError("PINNED_KEY_INVALID")
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, canonical(feed))
    except ReleaseError:
        raise
    except (ValueError, KeyError, TypeError) as err:
        raise ReleaseError("FEED_INVALID") from err
    except Exception as err:
        raise ReleaseError("SIGNATURE_NOT_VERIFIED") from err


def verify_archive(blob: bytes, target_version: str) -> dict:
    version_parts(target_version)
    if not isinstance(blob, bytes) or not 100 <= len(blob) <= MAX_ARCHIVE:
        raise ReleaseError("PACKAGE_SIZE_INVALID")
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except (ValueError, zipfile.BadZipFile) as err:
        raise ReleaseError("NOT_A_ZIP") from err
    with archive as z:
        entries = z.infolist()
        if not 2 <= len(entries) <= MAX_ITEMS:
            raise ReleaseError("PACKAGE_FILE_COUNT_INVALID")
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ReleaseError("DUPLICATE_PACKAGE_PATH")
        if set(names) - {"payload_manifest.json", "VERSION.txt"} and "VERSION.txt" not in names:
            raise ReleaseError("VERSION_MISSING")
        if "VERSION.txt" not in names or "payload_manifest.json" not in names:
            raise ReleaseError("REQUIRED_FILE_MISSING")
        total = 0
        for entry in entries:
            if entry.is_dir() or (entry.filename != "payload_manifest.json" and not APP_FILE.fullmatch(entry.filename)):
                raise ReleaseError("UNSAFE_PACKAGE_FILENAME")
            mode = (entry.external_attr >> 16) & 0xffff
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                raise ReleaseError("ZIP_SYMLINK_FORBIDDEN")
            if entry.flag_bits & 1 or entry.file_size > MAX_UNCOMPRESSED:
                raise ReleaseError("ZIP_ENCRYPTED_OR_SIZE_INVALID")
            total += entry.file_size
            if total > MAX_UNCOMPRESSED:
                raise ReleaseError("PACKAGE_UNCOMPRESSED_LIMIT")
        manifest_bytes = z.read("payload_manifest.json")
        if len(manifest_bytes) > 65536:
            raise ReleaseError("MANIFEST_TOO_LARGE")
        manifest = json.loads(manifest_bytes)
        if not isinstance(manifest, dict) or set(manifest) != {"version", "files"} or manifest["version"] != target_version:
            raise ReleaseError("PAYLOAD_MANIFEST_INVALID")
        files = manifest["files"]
        if not isinstance(files, dict) or set(files) != set(names) - {"payload_manifest.json"}:
            raise ReleaseError("PAYLOAD_FILE_SET_MISMATCH")
        if z.read("VERSION.txt").decode("ascii").strip() != target_version:
            raise ReleaseError("VERSION_POINTER_MISMATCH")
        for path, expected in files.items():
            if not SHA.fullmatch(expected) or hashlib.sha256(z.read(path)).hexdigest() != expected:
                raise ReleaseError("PAYLOAD_HASH_MISMATCH")
        return {"version": target_version, "sha256": hashlib.sha256(blob).hexdigest(),
                "size": len(blob), "files": len(files), "valid": True}


def verify_release(feed: dict, blob: bytes, *, installed_minimum: str | None = None,
                   public_key_hex: str = PINNED_PUBLIC_KEY_HEX) -> dict:
    assert_valid_feed(feed, public_key_hex)
    if installed_minimum and version_parts(feed["version"]) <= version_parts(installed_minimum):
        raise ReleaseError("DOWNGRADE_OR_SAME_VERSION")
    if len(blob) != feed["size"] or hashlib.sha256(blob).hexdigest() != feed["sha256"]:
        raise ReleaseError("SIGNED_PACKAGE_BYTES_MISMATCH")
    return verify_archive(blob, feed["version"])


def prepare_signed_feed(blob: bytes, version: str, seed_b64: str,
                        *, public_key_hex: str = PINNED_PUBLIC_KEY_HEX) -> dict:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    info = verify_archive(blob, version)
    try:
        raw = base64.b64decode(seed_b64, validate=True)
        if len(raw) != 32:
            raise ReleaseError("SIGNING_SEED_LENGTH")
        key = Ed25519PrivateKey.from_private_bytes(raw)
        pub = key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                            format=serialization.PublicFormat.Raw).hex()
        if pub != public_key_hex:
            raise ReleaseError("SIGNER_DOES_NOT_MATCH_INSTALLED_LAUNCHER")
        feed = {"version": version, "url": release_url(version), "size": info["size"],
                "sha256": info["sha256"], "signature": ""}
        feed["signature"] = key.sign(canonical(feed)).hex()
        assert_valid_feed(feed, public_key_hex)
        return feed
    except ReleaseError:
        raise
    except Exception as err:
        raise ReleaseError("SIGNER_INVALID") from err


def check_windows_qa(receipt: dict, version: str, archive_sha256: str) -> None:
    needed = ("launcher_ready", "zalo1_verified", "zalo2_verified",
              "unified_inbox_order", "sqlite_integrity", "rollback_tested", "no_auto_send")
    if not isinstance(receipt, dict) or receipt.get("schema") != "zalo-linh.windows-e2e.v1":
        raise ReleaseError("QA_SCHEMA_INVALID")
    if receipt.get("version") != version or receipt.get("release_zip_sha256") != archive_sha256:
        raise ReleaseError("QA_BUILD_IDENTITY_MISMATCH")
    checks = receipt.get("checks")
    if not isinstance(checks, dict) or any(checks.get(name) is not True for name in needed):
        raise ReleaseError("QA_NOT_COMPLETE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate signed Zalo Linh release without bypassing V7")
    sub = parser.add_subparsers(dest="action", required=True)
    v = sub.add_parser("verify", help="Verify the existing signed feed and release archive")
    v.add_argument("--feed", type=Path, required=True)
    v.add_argument("--zip", type=Path, required=True)
    v.add_argument("--installed-minimum")
    c = sub.add_parser("inspect", help="Validate a full candidate release ZIP (no signing)")
    c.add_argument("--zip", type=Path, required=True)
    c.add_argument("--version", required=True)
    c.add_argument("--installed-minimum", default="0.9.20")
    args = parser.parse_args()
    try:
        if args.action == "verify":
            data = json.loads(args.feed.read_text("utf-8"))
            report = verify_release(data, args.zip.read_bytes(), installed_minimum=args.installed_minimum)
        else:
            if version_parts(args.version) <= version_parts(args.installed_minimum):
                raise ReleaseError("DOWNGRADE_OR_SAME_VERSION")
            report = verify_archive(args.zip.read_bytes(), args.version)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (ReleaseError, OSError, UnicodeError, ValueError) as err:
        print(f"FAILED: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
