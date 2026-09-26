# Linh Edit 1.0

One local Windows video editor for Linh workflows.

## One app, four profiles

- Travel / Công tác
- Talk / Chuyên gia
- Tin tức
- Tuyển dụng

The old News and Editorial apps are migration sources/backups only after Windows
acceptance testing. MXH Video Editor/publishing remains separate and is not modified.

## Simple workflow

1. Add videos.
2. Choose a video type and target duration.
3. Optional: choose voiceover/music.
4. AUTO EDIT creates a rough cut following Linh Edit rules.
5. Adjust the timeline/text only if needed.
6. Preview.
7. Export final.

## Technical principles

- local FFmpeg/FFprobe rendering
- no cloud render credits required
- project JSON is human-readable and resumable
- render to temp -> QA -> atomic final replace
- 1080x1920 / 30fps / H.264 / AAC by default
- preview uses a lighter 540x960 render
- final export also creates a JPG cover
- old apps are never overwritten until Windows regression passes
