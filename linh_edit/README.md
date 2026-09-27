# Linh Edit 1.6

Linh Edit is the single local Windows editor for Linh video workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

Legacy News and Editorial apps remain untouched as rollback/migration sources.
MXH publishing stays separate.

## 1.6 — VO/Text/Audio Intelligence + safe live control

Version 1.6 builds on the proxy/shot/smart-layout engine from 1.5 and upgrades
the narration/text/audio layer while making direct ChatGPT edits safer when the
desktop app is open.

### Selective captions from VO script

Linh Edit now turns a transcript/VO script into selective body captions rather
than full subtitles.

- Hook 0–3s keeps ownership of opening text
- narration is split into compact 2–12 word blocks
- blocks are timed from the actual VO duration when a voice file is present
- only the more informative blocks are selected toward a configurable coverage
  target (default 65%)
- body captions stay lower-third and keep the Oswald caption style
- existing Hook layers are preserved when captions are regenerated

UI:
- **DÁN VO SCRIPT**
- **AUTO CAPTION VO**

CLI:
- `transcript-set`
- `caption-plan`
- `caption-apply`

### Text → Shot semantic matching

Caption text is classified into visual roles such as:

- road / travel → `road_reset`
- people / meetings → `human`
- work / administration → `work`
- place / landscape → `place`
- village / daily life → `life`
- kitchen / coffee / detail → `detail`
- emotional language → `emotion`

The apply path is deliberately conservative. It only swaps nearby timeline
slots when both source snippets are long enough to preserve the original slot
durations. This improves text–shot relevance without changing total runtime.

UI:
- **MATCH TEXT → SHOT**

CLI:
- `text-shot-report`
- `text-shot-apply`

### VO-first audio hierarchy

The local renderer now supports:

- independent VO gain
- automatic sidechain ducking of music under narration
- automatic ducking of retained source ambience under narration
- configurable threshold, ratio, attack and release
- existing SFX, music fades and limiter retained

UI:
- **AUDIO / DUCKING**

The Windows smoke test renders real synthetic VO + music through the sidechain
pipeline.

### Project revision safety + live reload

Project schema v4 adds an optimistic revision counter.

- every successful project save increments the revision
- stale saves are rejected instead of silently overwriting a newer project
- checkpoint restore keeps revision history monotonic
- the desktop app polls for external project changes
- when the UI has no unsaved local edits, newer ChatGPT/CLI changes reload
  automatically
- when local edits are dirty, Linh Edit warns instead of overwriting either side

This is the foundation for stable:
`ChatGPT → command → checkpoint → mutate → save revision → UI live reload`.

### 1.5 performance/visual intelligence retained

- reusable analysis proxies for heavy 4K/8K, HEVC, VFR/rotation/HDR footage
- bounded derived-data cache
- cached shot-boundary detection
- Source Review with KEEP / SHORTLIST / REJECT
- technical rank and duplicate warnings
- smart 9:16 reframe suggestions
- negative-space Hook placement
- reviewed-only rough-cut building
- normalization planning while final render stays on original footage

## Direct ChatGPT / Hub commands

Important automation commands now include:

- `proxy-build`
- `shot-detect`
- `source-review`
- `review-mark`
- `review-promote`
- `review-build`
- `normalization-plan`
- `hook-layout-apply`
- `transcript-set`
- `caption-plan`
- `caption-apply`
- `text-shot-report`
- `text-shot-apply`
- `project-patch`
- `project-checkpoint`
- `checkpoint-restore`
- `project-validate`
- `render`

## Review policy

Technical render completion is never treated as final editorial approval.

Final review remains:

1. Visual-only
2. Audio-only
3. Full playback without stopping

Exports remain `PENDING_PLAYBACK` until those checks are actually completed.

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
