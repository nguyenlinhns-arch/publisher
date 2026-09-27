# Legacy News migration into Linh Edit

The old News application is no longer the target host. It stays unchanged as a
rollback/migration source.

Live legacy root:

`D:\2 THAY_LINH_NEWS_VIDEO_APP_1.0.2\THAY_LINH_NEWS_VIDEO_APP_1.0.2`

The unified host is **Linh Edit 1.1**.

Migrated capabilities:

- ordinary text / legacy JSON ingestion
- deterministic scene splitting
- title/summary/voice_text normalization
- one-or-many image reuse
- transcript generation
- narration-weight timing and voice-duration resync
- preview/final local render
- legacy `script.json` import

The old News folder must not be overwritten or deleted until the unified app has
passed local Windows acceptance with real legacy projects.

MXH publishing remains outside Linh Edit.
