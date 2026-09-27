# Linh Edit 1.3

Linh Edit is the single local Windows editor for Linh video workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

The two legacy video apps remain untouched as rollback/migration sources.
MXH publishing stays separate.

## 1.3 — Footage review + safe direct editing

Version 1.3 keeps the unified local engine from 1.2 and adds a dedicated
source-review stage before rough cut.

### Source Review

For selected video footage, Linh Edit can now create a **Source Review Pack**:

- a 12-frame source contact sheet
- deterministic tile-to-time candidate windows
- technical audit score/warnings
- a JSON review manifest
- every candidate starts as `PENDING_VISUAL_REVIEW`
- visual quality is never auto-approved from metadata

Use the **DUYỆT FOOTAGE** button in the Media panel or the CLI command:

`source-review --media <video> --output-dir <folder>`

This is designed for the next selection pass: inspect shake, motion blur, face
crop, action quality, repeated visuals and emotional moments before promoting a
candidate into the timeline.

## Safety/control core retained from 1.2

- project schema v2 with backward loading
- atomic saves + source/transcript sidecars
- durable checkpoints and restore
- automatic checkpoints before destructive edit phases
- deterministic JSON project patches for ChatGPT/Hub
- project preflight validation before render
- technical footage audit before rough cut
- local FFmpeg/FFprobe rendering
- contact-sheet review
- true no-audio visual master
- technical render completion kept separate from playback review

## Direct control / automation

The local CLI exposes:

- `media-import`
- `news-import`
- `article-import`
- `legacy-import`
- `media-audit`
- `source-review`
- `project-status`
- `project-validate`
- `project-patch`
- `project-checkpoint`
- `checkpoint-list`
- `checkpoint-restore`
- `render`

Project patches are checkpointed first and rejected if they produce an invalid
project.

## Review policy

A successful render means only **technical render/QA passed**.

Final review still requires:

1. Visual-only review
2. Audio-only review
3. Full playback without stopping

Therefore final exports remain `PENDING_PLAYBACK` until those review passes are
actually completed.

## Legacy migration

Rollback source roots on the workstation:

- `D:\2 THAY_LINH_NEWS_VIDEO_APP_1.0.2\THAY_LINH_NEWS_VIDEO_APP_1.0.2`
- `D:\3 THAY_LINH_VIDEO_APP_EDITORIAL_1.7.0_FINAL`

Unified source root:

- `D:\LINH_EDIT`

Portable Windows builds include `LinhEdit.exe` and do not require a separate
Python installation for normal use.
