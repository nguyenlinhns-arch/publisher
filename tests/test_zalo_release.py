import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from zalo_linh_release import (
    DOMAIN, ReleaseError, assert_valid_feed, canonical, check_windows_qa,
    prepare_signed_feed, release_url, verify_archive, verify_release, version_parts,
)
from zalo_linh_release_drive import validate_input, beta_metadata, assert_file_id

SIGNED_0914 = json.loads((ROOT / 'zalo-linh' / 'channels' / 'stable.json').read_text('utf-8'))
SIGNED_ZIP = Path('/mnt/data/zalo-0.9.14.zip')


def make_pkg(version='0.9.21', evil=None, badhash=False, duplicate=False):
    app = 'app/zalo_runtime.py'
    contents = {'VERSION.txt': (version+'\n').encode(), app: b'print("safe")\n'}
    manifest = {'version': version,
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    if badhash:
        manifest['files'][app] = 'f' * 64
    with io.BytesIO() as mem:
        with zipfile.ZipFile(mem, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in contents.items():
                z.writestr(name, data)
            z.writestr('payload_manifest.json', json.dumps(manifest))
            if duplicate:
                z.writestr('VERSION.txt', '0.9.21\n')
            if evil:
                z.writestr(evil, b'malicious')
        return mem.getvalue()


def qa(version='0.9.21', sha='a'*64):
    return {'schema':'zalo-linh.windows-e2e.v1','version':version,'release_zip_sha256':sha,
            'checks': {'launcher_ready':True,'zalo1_verified':True,'zalo2_verified':True,
                       'unified_inbox_order':True,'sqlite_integrity':True,'rollback_tested':True,'no_auto_send':True}}


def test_signed_0914_real_bundle_verifies():
    assert_valid_feed(SIGNED_0914)
    if SIGNED_ZIP.exists():
        assert verify_release(SIGNED_0914, SIGNED_ZIP.read_bytes())['files'] == 12


def test_correct_canonical_domain_and_newline():
    expected=(f'{DOMAIN}\n0.9.14\n{SIGNED_0914["sha256"]}\n8655\n'
              'gdrive://ZaloLinhUpdates/releases/zalo-0.9.14.zip\n').encode()
    assert canonical(SIGNED_0914) == expected


def test_reject_old_as_upgrade():
    with pytest.raises(ReleaseError, match='DOWNGRADE'):
        verify_release(SIGNED_0914, b'not-used-because-downgrade-gate-first', installed_minimum='0.9.20')


def test_reject_forged_feed_signature():
    forged = {**SIGNED_0914, 'sha256': 'f' * 64}
    with pytest.raises(ReleaseError, match='SIGNATURE'):
        assert_valid_feed(forged)


def test_reject_unknown_feed_field():
    with pytest.raises(ReleaseError, match='FIELDS'):
        assert_valid_feed({**SIGNED_0914, 'command':'powershell'})


def test_reject_external_url():
    with pytest.raises(ReleaseError, match='URL'):
        assert_valid_feed({**SIGNED_0914, 'url':'http://example.com/malware'})


def test_reject_tampered_zip():
    with pytest.raises(ReleaseError, match='SIGNED_PACKAGE'):
        verify_release(SIGNED_0914, b'tampered-zip')


def test_candidate_full_zip_accepts():
    assert verify_archive(make_pkg(), '0.9.21')['files'] == 2


def test_previous_patch_toolkit_rejected_as_release():
    candidate = Path('/mnt/data/ZALO_LINH_0921_RC1_STAGING_UNSIGNED_20261024.zip')
    if candidate.exists():
        original = candidate.read_bytes()
    else:
        with io.BytesIO() as output:
            with zipfile.ZipFile(output, 'w') as zipout:
                zipout.writestr('BUNDLE_MANIFEST.json', '{}')
                zipout.writestr('prepare_zalo_linh_0921.py', 'pass\n')
            original = output.getvalue()
    with pytest.raises(ReleaseError, match='VERSION_MISSING|REQUIRED_FILE_MISSING'):
        verify_archive(original,'0.9.21')


def test_reject_zip_traversal():
    with pytest.raises(ReleaseError, match='UNSAFE_PACKAGE'):
        verify_archive(make_pkg(evil='../evil.py'),'0.9.21')


def test_reject_duplicate_zip_entries():
    with pytest.warns(UserWarning):
        pkg=make_pkg(duplicate=True)
    with pytest.raises(ReleaseError, match='DUPLICATE'):
        verify_archive(pkg,'0.9.21')


def test_reject_missing_manifest_hash_match():
    with pytest.raises(ReleaseError, match='HASH_MISMATCH'):
        verify_archive(make_pkg(badhash=True),'0.9.21')


def test_reject_wrong_expected_version():
    with pytest.raises(ReleaseError, match='MANIFEST_INVALID|VERSION'):
        verify_archive(make_pkg(),'0.9.22')


def test_signer_must_match_pinned_key():
    sk = Ed25519PrivateKey.generate()
    seed=sk.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
                          encryption_algorithm=serialization.NoEncryption())
    with pytest.raises(ReleaseError,match='SIGNER_DOES_NOT_MATCH'):
        prepare_signed_feed(make_pkg(),'0.9.21',base64.b64encode(seed).decode())


def test_generated_signature_roundtrip_using_test_key():
    sk = Ed25519PrivateKey.generate()
    public=sk.public_key().public_bytes(encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw).hex()
    seed=sk.private_bytes(encoding=serialization.Encoding.Raw,format=serialization.PrivateFormat.Raw,
                          encryption_algorithm=serialization.NoEncryption())
    pkg=make_pkg()
    feed=prepare_signed_feed(pkg,'0.9.21',base64.b64encode(seed).decode(),public_key_hex=public)
    assert verify_release(feed,pkg,installed_minimum='0.9.20',public_key_hex=public)['valid'] is True
    assert feed['url']==release_url('0.9.21')


def test_qa_receipt_all_checks_required():
    check_windows_qa(qa(), '0.9.21', 'a'*64)
    q=qa();q['checks']['rollback_tested']=False
    with pytest.raises(ReleaseError,match='QA_NOT_COMPLETE'):
        check_windows_qa(q,'0.9.21','a'*64)


def test_qa_receipt_binds_to_exact_zip():
    with pytest.raises(ReleaseError,match='QA_BUILD_IDENTITY'):
        check_windows_qa(qa(),'0.9.21','b'*64)


def test_no_old_version_publish():
    with pytest.raises(ReleaseError,match='MINIMUM_PRODUCTION'):
        validate_input('0.9.20','a'*64)


def test_no_invalid_sha_publish():
    with pytest.raises(ReleaseError,match='SHA256'):
        validate_input('0.9.21','bad')


def test_drive_file_id_strict():
    assert assert_file_id('1DvCMqDK8mgirMOGRmUL5QICDEfHY7834')
    with pytest.raises(ReleaseError,match='FILE_ID_INVALID'):
        assert_file_id('https://drive.google.com/file/d/evil/view')


def test_beta_is_uninstallable_metadata_only():
    b=beta_metadata('0.9.21','a'*64,200)
    assert b['installable'] is False
    assert b['schema']=='zalo-linh.channel-beta.v1'
    with pytest.raises(ReleaseError):
        assert_valid_feed(b)


def test_versions_numeric_and_fixed():
    assert version_parts('0.9.21') > version_parts('0.9.20')
    for value in ('0.9.021','0.9','1.2.3-alpha','../evil','1000.0.1'):
        with pytest.raises(ReleaseError):
            version_parts(value)
