# Third-party notices

MXH Publisher bundles and depends on third-party software. Copyright and
license notices for those components remain the property of their respective
authors.

## FFmpeg / ffprobe 8.1.2

The Windows package includes `ffprobe.exe` from the Gyan FFmpeg 8.1.2
Essentials Build.

- Project: <https://ffmpeg.org/>
- Windows build provider: <https://www.gyan.dev/ffmpeg/builds/>
- Exact archive:
  <https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-essentials_build.zip>
- Archive SHA-256:
  `db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec`
- Corresponding FFmpeg source revision linked by the build provider:
  <https://github.com/FFmpeg/FFmpeg/commit/38b88335f9>
- License reported by the build provider: GNU GPL version 3.

`ffprobe.exe` is a separate executable invoked by MXH Publisher. The packaging
process copies the license and README shipped in the downloaded FFmpeg archive
into `licenses/ffmpeg/` when those files are present. The build also records
the archive and executable SHA-256 values in `licenses/ffmpeg/SOURCE.txt`.

The GNU GPL version 3 text and source information are available at:

- <https://www.gnu.org/licenses/gpl-3.0.html>
- <https://ffmpeg.org/legal.html>
- <https://ffmpeg.org/download.html#get-sources>

## Playwright

Playwright is licensed under the Apache License 2.0. Its Python package and
driver retain their bundled `LICENSE`, `NOTICE`, and `ThirdPartyNotices.txt`
files inside the PyInstaller onedir distribution.

- <https://github.com/microsoft/playwright-python>
- <https://www.apache.org/licenses/LICENSE-2.0>

Other Python dependencies retain their package metadata and applicable notices
inside the application bundle. This file is informational and is not legal
advice.
