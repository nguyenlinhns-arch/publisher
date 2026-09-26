# Linh Edit — Windows migration

Target:
D:\LINH_EDIT

Legacy applications stay untouched during rollout:
- D:\THAY_LINH_NEWS_VIDEO_APP_1.0.2\THAY_LINH_NEWS_VIDEO_APP_1.0.2
- D:\THAY_LINH_VIDEO_APP_EDITORIAL_1.7.0_FINAL

Explicitly out of scope:
- D:\MXHVideoTools-1.8.0-Windows-x64

Rollout order:
1. Make a checkpoint/read-only inventory of both legacy app roots.
2. Put the portable LinhEdit build in D:\LINH_EDIT.
3. Run: LinhEdit.exe doctor.
4. Run: LinhEdit.exe capabilities.
5. Open the GUI and verify project create/save/load.
6. Import a short real video and verify preview.
7. Render a short 1080x1920 final and verify QA JSON + JPG cover.
8. Test TRAVEL_DOCUMENTARY with the Gia Lai project.
9. Only after acceptance, use Linh Edit as the daily editor. Keep old apps for rollback until a later explicit cleanup decision.

Do not merge MXH publishing into Linh Edit.
Do not delete old apps during the first production rollout.
