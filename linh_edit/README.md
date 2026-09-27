# Linh Edit 1.2

Linh Edit is the single local Windows editor for the Linh video workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

The two older video apps remain untouched as rollback/migration sources.
MXH publishing stays separate.

## 1.2: safer, more controllable local editing

Linh Edit 1.2 keeps the 1.1 unified engine and adds a control/safety layer for
daily work and direct ChatGPT/Hub operation:

- versioned project schema with backward migration
- atomic project saves plus source/transcript sidecars
- durable checkpoints with restore
- automatic checkpoints before rough cut, text, audio, SFX, destructive timeline edits and export
- safe deterministic JSON project patches for remote/ChatGPT editing
- project preflight validation before render
- technical media audit before rough cut
- hard rejection of technically unusable footage while leaving blur/shake/composition for visual review
- explicit TECHNICAL_DONE vs playback-review PENDING state
- contact sheet review
- true visual master without an audio stream
- Windows local render, QA and versioned outputs

## Unified source workflows

### Direct footage

Use Travel, Talk or Recruitment profiles with normal footage/media import.
The rough-cut planner preserves the Linh Edit story DNA and scores technical
suitability before selection.

### News / Editorial

Use either:

- **DÁN NEWS / JSON**
- **VIDEO TỪ LINK BÀI VIẾT**
- **Tệp -> Nhập dự án app cũ (script.json)...**

Linh Edit creates or preserves the canonical transcript, scene order, image
order and selected audio. News/Editorial timelines can be re-timed to the real
voice duration.

## Direct control / automation

The local CLI exposes deterministic commands that do not require GUI clicking:

- `media-import`
- `news-import`
- `article-import`
- `legacy-import`
- `media-audit`
- `project-status`
- `project-validate`
- `project-patch`
- `project-checkpoint`
- `checkpoint-list`
- `checkpoint-restore`
- `render`

Every project patch creates a checkpoint first and validates the resulting
project before committing it.

## Review policy

A successful render means the technical render/QA passed. It does **not** mean
the edit has passed playback review.

Final review remains:

1. Visual-only review
2. Audio-only review
3. Full playback without stopping

QA files therefore keep visual/audio/style review states as pending until those
passes are completed.

## Legacy migration

Known rollback sources on the workstation:

- `D:\2 THAY_LINH_NEWS_VIDEO_APP_1.0.2\THAY_LINH_NEWS_VIDEO_APP_1.0.2`
- `D:\3 THAY_LINH_VIDEO_APP_EDITORIAL_1.7.0_FINAL`

Target unified install root:

- `D:\LINH_EDIT`

The legacy source folders are not modified.
