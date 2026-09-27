# Linh Edit 1.5

Linh Edit is the single local Windows editor for Linh video workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

Legacy News and Editorial apps remain untouched as rollback/migration sources.
MXH publishing stays separate.

## 1.5 — Performance + Shot Intelligence + Smart Layout

Version 1.5 keeps the reviewed-selection loop from 1.4 and makes it practical
for large phone/camera footage libraries.

### Proxy + analysis cache

Heavy footage no longer needs to be re-decoded at full quality for every review.

- 4K/8K, HEVC, VFR, rotated and HDR-sensitive sources can use a local analysis proxy
- proxies are H.264, analysis-only, muted and capped at 30fps
- final render continues to use the original source
- cache keys include source path + size + mtime
- unchanged sources reuse cached proxies and shot analysis
- Source Review analysis is cached and manual KEEP/SHORTLIST/REJECT decisions survive rebuilds
- derived cache is bounded and can be pruned without touching original footage

CLI:
- `proxy-build`
- `cache-status`
- `cache-prune`

### Shot-boundary review

Source Review now prefers actual scene/shot boundaries instead of only uniform
time sampling.

- FFmpeg scene detection is cached
- candidate windows stay inside detected shot boundaries
- review still falls back safely to uniform sampling if scene detection fails
- the contact sheet is therefore more likely to represent genuinely different shots

CLI:
- `shot-detect`
- `source-review`

### VFR / rotation / HDR awareness

Linh Edit now reads:

- average and nominal frame rate
- VFR status
- rotation metadata
- pixel format
- color transfer / space / primaries

The app produces a normalization plan rather than destructively transcoding
source footage. Original media remains the final-render source.

CLI:
- `normalization-plan`

### Smart 9:16 reframe

Candidate analysis now estimates a local visual-saliency center and stores
9:16 crop suggestions.

- landscape footage gets a suggested x/y crop
- portrait-native footage stays centered when no crop is needed
- the suggestion is carried into KEEP promotion and reviewed-only rough cuts
- this is a visual heuristic, not face/person recognition, so it never bypasses review

### Hook layout intelligence

For each reviewed candidate Linh Edit estimates:

- negative-space region
- CENTER / UPPER-CENTER / CENTER-LEFT placement
- CLEAN vs HIGH_CONTRAST recommendation
- Hook x/y/alignment
- layout confidence

The review UI shows the suggested reframe and Hook layout. A KEEP candidate can
apply its placement to existing Context/Main/Keyword Hook layers with a
checkpoint first.

CLI:
- `hook-layout-apply`

### Review loop retained from 1.4

- individual candidate thumbnails
- technical rank
- brightness / contrast / edge-detail hints
- perceptual duplicate warnings across footage
- KEEP / SHORTLIST / REJECT
- role assignment
- candidate promotion
- **ROUGH CUT TỪ TẤT CẢ KEEP**

Only explicit KEEP candidates enter the reviewed automation path.

## Direct ChatGPT / Hub commands

- `media-import`
- `media-audit`
- `proxy-build`
- `shot-detect`
- `source-review`
- `review-mark`
- `review-promote`
- `review-build`
- `hook-layout-apply`
- `normalization-plan`
- `cache-status`
- `cache-prune`
- `project-status`
- `project-validate`
- `project-patch`
- `project-checkpoint`
- `checkpoint-list`
- `checkpoint-restore`
- `news-import`
- `article-import`
- `legacy-import`
- `render`

## Safety / review policy

- project schema v2
- atomic saves
- source/transcript sidecars
- durable checkpoints
- preflight validation before render
- original footage is never replaced by proxies
- cache contains only disposable derived data
- technical scoring never auto-approves visual quality
- technical render completion is not playback approval

Final review remains:

1. Visual-only
2. Audio-only
3. Full playback without stopping

## Windows app

The portable Windows build contains:

- `LinhEdit.exe`
- FFmpeg / FFprobe
- Montserrat + Oswald
- Pillow visual-analysis runtime
- Hub lifecycle files

Normal use does not require a separate Python installation.

Unified source root:

- `D:\LINH_EDIT`
