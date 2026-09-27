# Linh Edit 2.0

Linh Edit is the unified local Windows editor for the Linh video workflow.

It replaces the need to operate the old News and Editorial editors separately,
while keeping those legacy folders untouched for rollback. MXH publishing
remains a separate app/workflow.

## Profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

Default output remains vertical 1080×1920 at 30fps.

## Core workflow

Story → Source Review → Select → Rough Cut → Reframe → Hook → Selective Text →
Audio → Color/HDR → Cover → Automated QA → Review 3 Pass → Export/Publish-ready.

The app intentionally prefers hard cuts, real footage, selective text and
natural documentary pacing over heavy transitions or decorative FX.

## Media intelligence

### Proxy + cache

Heavy sources such as 4K/8K, HEVC, VFR, rotated and HDR footage can use
disposable local analysis proxies. Final render always reads the original
source.

The cache is fingerprinted by path, size and mtime, reused when safe, bounded,
and can be pruned without touching source footage.

### Shot-aware Source Review

Linh Edit prefers real shot boundaries over uniform sampling, then creates:

- candidate time windows
- contact sheets
- individual review frames
- brightness / contrast / edge-detail hints
- perceptual duplicate warnings
- technical rank
- KEEP / SHORTLIST / REJECT state
- role assignment

Technical heuristics never auto-approve visual quality.

### Face/person-aware reframe

OpenCV-based local subject intelligence now detects and tracks faces or people
across multiple frames of a candidate. The tracked center improves 9:16
reframe placement. If detection is unavailable or uncertain, Linh Edit falls
back to local visual-saliency analysis.

No face identity recognition is performed.

### Hook intelligence

For reviewed candidates Linh Edit estimates:

- negative-space region
- CENTER / UPPER-CENTER / CENTER-LEFT placement
- CLEAN vs HIGH_CONTRAST
- Hook x/y/alignment
- layout confidence

A KEEP candidate can apply its layout to Context/Main/Keyword Hook layers with
a checkpoint first.

## Story and rhythm intelligence

### Travel Story Optimizer

Travel rough cuts use the project DNA:

visual hook → human → work → road reset → place → detail/life → emotion →
lingering ending.

The optimizer limits work/admin dominance, rewards source diversity, preserves
reviewed/manual selections, keeps road resets when available, and gives
human/emotion/ending shots longer holds.

### Talk Rhythm

Talk projects can detect VO silence with FFmpeg and fall back to transcript
punctuation. The source is split at phrase boundaries while preserving total
runtime, then receives subtle alternating 1.0 / 1.035 punch rhythm rather than
continuous zooming.

## VO, text and semantic matching

### Selective captions

VO script/transcript is split into compact narration blocks. Hook owns 0–3s;
body captions are selective rather than full subtitles, with a configurable
coverage target (default 65%).

### Text → Shot matching

Narration concepts such as road, people, work, place, daily life, detail and
emotion are mapped to visual roles. The automatic apply path only swaps nearby
timeline slots when duration constraints remain safe.

## Audio intelligence

- independent VO and music gain
- source ambience hierarchy
- sidechain ducking under VO
- configurable threshold / ratio / attack / release
- LUFS measurement
- automatic VO/music stem balancing
- final loudness mastering (default -14 LUFS, -1.5 dBTP, LRA 11)
- final limiter retained

The one-command optimization pipeline can measure source loudness and prepare
the mix before render.

## Color and HDR

Linh Edit reads VFR, rotation, pixel format and color metadata. HDR10/PQ and
HLG sources can be tone-mapped to natural BT.709 SDR in analysis proxies and
final SDR output while the original source file remains untouched.

## Automated final QA

Every render keeps the technical QA and also writes an editorial QA report with:

- output geometry / fps / codecs / duration
- black-span detection
- long-silence detection
- final loudness / true peak
- shot-count and average-shot metrics
- work ratio
- road reset / human / emotion counts
- source repetition
- caption coverage
- Hook completeness
- current Review 3 Pass state

Automated QA is advisory. It never replaces playback review.

## Safe direct ChatGPT / Hub control

Project schema v6 separates:

- save revision
- content revision
- review content revision

Stale writers are rejected. A clean desktop project live-reloads after safe
CLI/ChatGPT edits; dirty local edits are protected from overwrite.

The main automation command is:

- `optimize-all`

It performs the profile-appropriate story/rhythm pass, selective captions,
conservative text-shot matching where applicable, automatic audio balancing,
validation and an optional render, then writes a durable pipeline receipt.

Advanced deterministic commands remain available for individual phases such as
`source-review`, `review-build`, `caption-apply`, `text-shot-apply`,
`audio-auto-master`, `qa-analyze`, `project-patch` and `render`.

## Review 3 Pass

Publication readiness requires the current content revision to have:

1. VISUAL ONLY = PASS
2. AUDIO ONLY = PASS
3. FULL PLAYBACK = PASS

Any later editorial change or checkpoint restore makes earlier approvals stale.
Only then does project status become READY_TO_PUBLISH.

## Windows package

The portable package includes:

- `LinhEdit.exe`
- FFmpeg / FFprobe
- OpenCV face/person intelligence
- Pillow visual analysis
- Montserrat + Oswald
- Hub lifecycle files

Normal operation does not require a separate Python installation.

Unified source root:

- `D:\LINH_EDIT`

Legacy rollback roots remain untouched.
