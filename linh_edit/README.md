# Linh Edit 1.4

Linh Edit is the single local Windows editor for Linh video workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

Legacy News and Editorial apps remain untouched as rollback/migration sources.
MXH publishing stays separate.

## 1.4 — Visual Selection Loop

Version 1.4 upgrades the footage-selection stage from a technical file audit to
a reviewable visual workflow.

### Source Review Pack

For selected footage Linh Edit creates:

- a 12-frame source contact sheet
- individual candidate frames
- brightness / contrast / edge-detail metrics
- per-source technical rank
- perceptual-hash duplicate warnings inside and across footage
- deterministic candidate time windows
- an auditable JSON review manifest

The metrics are only **technical heuristics**. They never automatically approve
a shot. Face crop, shake, motion blur, action quality, emotion and composition
still require visual review.

### Integrated review UI

The **DUYỆT FOOTAGE** flow now opens a review window inside Linh Edit with:

- candidate thumbnail preview
- source/time/rank/technical-score readback
- duplicate flags and warnings
- KEEP / SHORTLIST / REJECT decisions
- role assignment before promotion
- one-candidate promotion into the timeline
- **ROUGH CUT TỪ TẤT CẢ KEEP** to build a reviewed-only rough cut

Only candidates explicitly marked **KEEP** can be promoted by the review
automation path.

### ChatGPT / Hub direct workflow

The CLI exposes the same deterministic flow without GUI clicking:

- `source-review`
- `review-mark`
- `review-promote`
- `review-build`
- `project-patch`
- `project-checkpoint`
- `checkpoint-restore`
- `project-validate`
- `render`

This allows ChatGPT to create review packs, inspect/mark selected candidates,
promote only approved footage, build a rough cut, patch text/audio/timeline and
render through the same Linh Edit project model.

## Safety core retained

- project schema v2 with backward loading
- atomic project saves
- source/transcript sidecars
- durable checkpoints
- automatic checkpoints before destructive phases
- preflight validation before render
- technical footage rejection for unusable sources
- local FFmpeg/FFprobe render
- contact-sheet review
- versioned outputs
- true no-audio visual master

## Review policy

A successful render means **technical render/QA passed**, not that the edit is
finished.

Final review remains:

1. Visual-only
2. Audio-only
3. Full playback without stopping

Exports remain `PENDING_PLAYBACK` until those passes are actually completed.

## Windows app

The portable Windows build contains:

- `LinhEdit.exe`
- bundled FFmpeg / FFprobe
- Montserrat + Oswald typography assets
- Pillow visual-review runtime
- Hub manifest / launcher / health check

Normal use does not require a separate Python installation.

## Local roots

Unified source root:

- `D:\LINH_EDIT`

Legacy rollback sources:

- `D:\2 THAY_LINH_NEWS_VIDEO_APP_1.0.2\THAY_LINH_NEWS_VIDEO_APP_1.0.2`
- `D:\3 THAY_LINH_VIDEO_APP_EDITORIAL_1.7.0_FINAL`
