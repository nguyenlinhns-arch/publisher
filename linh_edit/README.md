# Linh Edit 1.7

Linh Edit is the single local Windows editor for Linh video workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

Legacy News and Editorial apps remain untouched as rollback/migration sources.
MXH publishing stays separate.

## 1.7 — Story Rhythm + Three-Pass Review Gate

Version 1.7 builds on the 1.6 VO/Text/Audio layer and makes story rhythm and
final editorial review first-class project state.

### Constraint-based Travel Story Optimizer

Travel rough cuts now use a deterministic story optimizer instead of a simple
role loop.

It targets the Linh documentary arc:

- visual hook
- human
- work
- road reset
- place
- detail / life
- emotion
- lingering ending

The optimizer:

- caps work/admin footage as a minority of total runtime
- rewards source diversity and avoids needless repeated snippets
- preserves road resets when source footage is available
- gives human/emotion shots longer holds than work/admin shots
- keeps hard-cut structure
- pushes an ending shot to the tail when available
- reports work ratio, road-reset count, source diversity and final role order

UI:
- **STORY OPTIMIZE**

CLI:
- `story-optimize`

Travel **AUTO EDIT** is routed through this optimizer.

### Talk Rhythm — punch-in / punch-out at phrase boundaries

Talk / Expert projects can now use sentence-aware rhythm without continuous
zoom effects.

Linh Edit:

- detects VO silence with FFmpeg when a voice track is available
- falls back to transcript punctuation timing when silence detection has no
  useful boundary
- splits the existing source clip without changing total runtime
- alternates a subtle 1.0 / 1.035 punch scale at phrase boundaries
- keeps original source time continuity and audio

UI:
- **TALK RHYTHM**

CLI:
- `talk-rhythm-apply`

### Three-Pass Review Gate

Visual-only, Audio-only and Full Playback are now stored as project review
state instead of only being notes in a QA file.

States:

- PENDING
- PASS
- FAIL

A project becomes **READY_TO_PUBLISH** only when all three passes are PASS for
the current content revision.

If the edit changes later:

- `content_revision` increments
- earlier review approvals automatically become stale
- the project is no longer READY_TO_PUBLISH until reviewed again

UI:
- **REVIEW 3 PASS**
- File menu → Review 3 pass

CLI:
- `review-status`
- `review-set`
- `review-reset`

### Safer live ChatGPT + desktop editing

Project schema v5 separates:

- save revision — protects against simultaneous writers
- content revision — tracks editorial changes
- review content revision — binds review approval to the exact edit

Stale cross-process saves remain blocked. Checkpoint restore now counts as a
content change, so restoring an older edit automatically invalidates stale
review approvals.

### 1.6 intelligence retained

- selective captions from VO script
- DÁN VO SCRIPT / AUTO CAPTION VO
- conservative text-to-shot matching
- VO-first music ducking
- retained source ambience ducking under VO
- configurable threshold / ratio / attack / release
- project live reload after safe external edits

### 1.5 performance/visual intelligence retained

- 4K/8K/HEVC/VFR/HDR analysis proxies
- reusable bounded cache
- shot-boundary Source Review
- KEEP / SHORTLIST / REJECT
- perceptual duplicate warnings
- smart 9:16 reframe suggestions
- negative-space Hook layout suggestions
- reviewed-only rough-cut building
- final render always uses original source footage

## Direct ChatGPT / Hub commands

The deterministic command layer includes:

- `story-optimize`
- `talk-rhythm-apply`
- `review-status`
- `review-set`
- `review-reset`
- `transcript-set`
- `caption-plan`
- `caption-apply`
- `text-shot-report`
- `text-shot-apply`
- `source-review`
- `review-mark`
- `review-promote`
- `review-build`
- `hook-layout-apply`
- `proxy-build`
- `shot-detect`
- `normalization-plan`
- `project-patch`
- `project-checkpoint`
- `checkpoint-restore`
- `project-validate`
- `render`

## Review policy

A successful render means technical render/QA passed.

Publication readiness still requires:

1. Visual-only PASS
2. Audio-only PASS
3. Full Playback PASS

Any later content edit invalidates those approvals automatically.

## Windows app

The portable Windows package contains:

- `LinhEdit.exe`
- FFmpeg / FFprobe
- Montserrat + Oswald
- Pillow visual-analysis runtime
- Hub lifecycle files

Normal use does not require a separate Python installation.

Unified source root:

- `D:\LINH_EDIT`
