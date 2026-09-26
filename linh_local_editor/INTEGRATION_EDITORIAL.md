# Integration target: THAY LINH VIDEO APP EDITORIAL 1.7.0 FINAL

Host root already identified on the Windows PC:
D:\THAY_LINH_VIDEO_APP_EDITORIAL_1.7.0_FINAL

This package is an add-on, not a replacement app.

## Non-negotiable integration rules

1. Checkpoint/copy the current working app before any mutation.
2. Keep MO_UNG_DUNG.bat unchanged unless source inspection proves a launcher change is required.
3. Do not change existing manual edit behavior.
4. Add one host action/menu/button: "LINH AUTO EDIT".
5. The host owns project/timeline state; the engine owns deterministic render of an explicit plan.
6. Profiles exposed to the host:
   - Travel / Công tác
   - Talk / Chuyên gia
   - Tin tức / Editorial
   - Tuyển dụng trực tiếp
7. Rendering is local via FFmpeg/FFprobe. No cloud render or paid API is required.
8. Never write into MXH Video Editor or publishing folders.
9. Render to a new versioned output; do not overwrite a known-good master.
10. QA gate: ffprobe geometry/codec/fps + full decode before final replace.

## First UI integration

The existing Editorial UI should expose:
- Profile selector
- Add footage
- Add VO
- Add optional music
- Target duration
- "Phân tích / Tạo rough cut"
- Timeline/manual adjustments (existing host behavior)
- "Render Preview"
- "Export Final"

The first production target is TRAVEL_DOCUMENTARY using the Gia Lai footage.
