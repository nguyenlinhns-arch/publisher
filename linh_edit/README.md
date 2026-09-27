# Linh Edit 1.1

Linh Edit is the single local Windows editor for the Linh video workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức / Editorial
- Tuyển dụng

The two older video apps remain untouched as rollback/migration sources until
local Windows acceptance is complete. MXH publishing stays separate.

## What 1.1 consolidates

### From THAY LINH NEWS VIDEO APP

- paste ordinary Vietnamese news text or legacy JSON
- deterministic scene splitting and canonical transcript
- reuse one or many selected images across scenes
- allocate scene duration from narration weight
- resync the whole story to the real selected voice duration
- preview/final local render and versioned output
- import an existing legacy `script.json`

### From THAY LINH VIDEO APP EDITORIAL

- create video from a public article URL
- extract source title/description/paragraphs and real article images locally
- reject private/loopback/internal URL targets
- deterministic, source-grounded storyboard
- transcript-first workflow; the app does not create TTS
- import legacy Editorial `hero/card` projects into the same Linh Edit timeline

### Linh Edit DNA

- Hook 3 layers: Context / Main / Keyword
- Montserrat for hook hierarchy
- Oswald for selective body captions
- local FFmpeg/FFprobe rendering
- 1080x1920 / 30fps output by default
- render to temporary output -> QA -> atomic final
- no cloud render credits required
- final export creates a JPG cover
- existing final files are versioned instead of overwritten

## Unified workflow

1. Choose one source:
   - add footage/media directly,
   - **DÁN NEWS / JSON**, or
   - **VIDEO TỪ LINK BÀI VIẾT**.
2. For News/Editorial, open the generated transcript if a voice track is needed.
3. Create/select the voice file externally, then choose it in Linh Edit.
4. Linh Edit re-times News/Editorial scenes to the real voice duration.
5. Review the timeline, Hook and selective captions.
6. Preview.
7. Export final.

## Legacy migration

Use **Tệp -> Nhập dự án app cũ (script.json)...** and select the old
`script.json`.

Linh Edit reads both UTF-8 and Windows UTF-8 BOM files. It also reuses a legacy
voice only when the old `transcript.txt` still matches the imported narration.
The legacy source folders are not modified.

Known legacy roots on the workstation:

- `D:\2 THAY_LINH_NEWS_VIDEO_APP_1.0.2\THAY_LINH_NEWS_VIDEO_APP_1.0.2`
- `D:\3 THAY_LINH_VIDEO_APP_EDITORIAL_1.7.0_FINAL`

Target unified install root:

- `D:\LINH_EDIT`
