# Linh Edit Engine — local add-on

This directory is an add-on module intended to be embedded into the existing
THAY LINH VIDEO APP EDITORIAL application. It is not a standalone application
and must not replace the existing launcher or project state.

Goals:
- local-only render path (FFmpeg/FFprobe)
- deterministic edit plans
- profile routing: travel documentary, talking head, explainer/news, recruitment
- preserve existing host UI and manual editing
- no cloud credit dependency for rendering
- no coupling to MXH Video Editor / publishing flows

Host integration is intentionally thin: the existing Editorial app should call
linh_edit_engine.api from its own menu/button/action layer.
