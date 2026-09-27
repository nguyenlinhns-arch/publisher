# Linh local editor transition notes

This directory is historical integration documentation.

The current architecture is one standalone Windows application: **Linh Edit**.
The old News and Editorial programs are migration/rollback sources, not hosts for
new Linh Edit code.

Current principles:

- one local editor for Travel, Talk, News/Editorial and Recruitment
- deterministic local FFmpeg/FFprobe render
- one project/timeline model
- legacy project import without mutating legacy folders
- no cloud rendering dependency
- no coupling to MXH Video Editor or social publishing

New implementation work belongs under `linh_edit/`.
