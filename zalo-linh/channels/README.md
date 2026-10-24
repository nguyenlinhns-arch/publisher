# Zalo Linh — release channels

- `zalo-linh/stable.json` (repository's existing production mirror) and
  `G:\My Drive\ZaloLinhUpdates\stable.json` are **signed production** manifests.
  The installed fixed launcher validates Ed25519, SHA-256, ZIP members and version.
- `channels/stable.json` is a copy of the currently signed stable pointer; it is
  **not a separate auto-update endpoint**.
- `channels/beta.json` is **metadata only** for internal QA. It is not signed,
  may point to an unsigned staging *toolkit*, and must never be consumed by the
  installed launcher/Guard as an update.
- `versions/<version>` & `previous.txt` on the PC remain the source of rollback;
  this repository never writes the PC's version pointers or Zalo profiles.

**Signing is owned by the machine/release administrator.** The GitHub workflow
`zalo-linh-signed-release.yml` requires a protected `zalo-linh-production`
environment, a Drive service account shared with ONLY the release/staging
folders, and a matching Ed25519 signing seed kept as GitHub secrets. No signing
key or Zalo login secret is stored in repository source or sent to ChatGPT.

The workflow refuses `stable` publication unless a full `zalo-<version>.zip`
contains a verified payload manifest, its version exceeds 0.9.20, and a private
Windows E2E QA receipt binds to its SHA-256. It publishes the release to Drive,
then the signed stable manifest and a GitHub metadata mirror. Until all gates
pass, **installed version 0.9.20 is left unchanged**.

To switch on unattended installation once: an owner must approve the locally
installed fixed ZaloLinh.exe / AutoUpdateGuard task and its narrowed signed
`check_update`/`apply_update` recipes through the PC's local administrator.
Remote V7 `open/ui` approval is NOT code-update or signer authority. Do not
circumvent `POLICY_DENIED`, SmartScreen, UAC, or signature enforcement.
