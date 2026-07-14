# Third-party notices

MXH Video Editor bundles and depends on third-party software. Copyright and
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

`ffmpeg.exe` and `ffprobe.exe` are separate executables invoked by MXH Video
Editor. The packaging
process copies the license and README shipped in the downloaded FFmpeg archive
into `licenses/ffmpeg/` when those files are present. The build also records
the archive and executable SHA-256 values in `licenses/ffmpeg/SOURCE.txt`.

The GNU GPL version 3 text and source information are available at:

- <https://www.gnu.org/licenses/gpl-3.0.html>
- <https://ffmpeg.org/legal.html>
- <https://ffmpeg.org/download.html#get-sources>

MXH Video Editor does not bundle Playwright or browser automation libraries.
This file is informational and is not legal advice.

## Oswald, Montserrat and Be Vietnam Pro

The application uses Oswald Bold for news headlines and Be Vietnam Pro
SemiBold for the brand line. Montserrat is retained as a bundled fallback.
All three font families are available under the SIL Open Font License 1.1. The license text is
included at `assets/fonts/OFL.txt` in the source and application bundle.

- <https://github.com/googlefonts/OswaldFont>
- <https://github.com/google/fonts/tree/main/ofl/bevietnampro>
- <https://github.com/JulietaUla/Montserrat>
- <https://openfontlicense.org/>
