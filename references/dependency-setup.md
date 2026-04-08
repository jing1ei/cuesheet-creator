# Dependency Setup & Environment Preparation

## Prerequisites

- **Python >= 3.10**
- **ffmpeg / ffprobe available either on PATH or from a local portable directory**
- Optional ASR/OCR/SceneDetect components may download models on first run

> **Windows / PowerShell**: Quote paths with spaces. Use full path to `scripts/cuesheet_creator.py` if not in project root.

> **Windows FFmpeg recommendation**: Prefer a portable FFmpeg copy under `<skill-root>/tools/ffmpeg/`. cuesheet-creator auto-detects both `<skill-root>/tools/ffmpeg/bin/ffmpeg.exe` and a nested release folder such as `<skill-root>/tools/ffmpeg/ffmpeg-7.x-essentials_build/bin/ffmpeg.exe`. If you keep FFmpeg elsewhere, set `CUESHEET_CREATOR_FFMPEG_BIN_DIR` for the current shell.


## Goal

Give cuesheet-creator a clear, selectable, one-command environment preparation flow:

- `check-only`: Environment check only, no installs
- `install-required`: Auto-install missing required Python packages
- `install-scene`: Required packages + SceneDetect (enhanced cut detection)
- `install-asr`: Required packages + ASR optional components
- `install-ocr`: Required packages + OCR primary engine (rapidocr-onnxruntime)
- `install-ocr-extra`: Required packages + OCR primary + alternative engines (easyocr, paddleocr)
- `install-all`: Required packages + scene + asr + ocr (**aligned with `pip install .[all]`** — does NOT include ocr-extra)
- `install-everything`: Required packages + every optional group including ocr-extra

> **Note**: `install-all` and `pip install .[all]` install the same set: scene detection, ASR, and the primary OCR engine (rapidocr). Alternative OCR engines (easyocr, paddleocr) are heavier dependencies — use `install-ocr-extra` or `install-everything` if you need them.

> **`install-deps --include-optional`** accepts the same keywords: `none`, `scene`, `asr`, `ocr`, `ocr-extra`, `all`, `everything` (comma-separated). `all` = scene+asr+ocr; `everything` = all supported groups.

## Recommended entry: prepare-env

### 1. Check only

```bash
python scripts/cuesheet_creator.py prepare-env --mode check-only --out-dir <out-dir>
```

### 2. Install required Python packages

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-required --out-dir <out-dir>
```

### 3. Add SceneDetect (enhanced cut detection)

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-scene --out-dir <out-dir>
```

### 4. Add ASR components

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-asr --out-dir <out-dir>
```

### 5. Add OCR components

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-ocr --out-dir <out-dir>
```

### 6. Full install

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-all --out-dir <out-dir>
```

When `--out-dir` is provided, the following files are automatically written:

- `<out-dir>/prepare_env.json`
- `<out-dir>/selfcheck.pre.json`
- `<out-dir>/selfcheck.post.json`
- `<out-dir>/install_report.json` (only when install steps are executed)

`prepare-env` chains three steps:

1. Initial `selfcheck`
2. Install based on mode (if applicable)
3. Final `selfcheck`

Default: only pass `--out-dir`. To override specific file names:

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-required --out-dir <out-dir> --selfcheck-out <custom>/pre.json --install-report-out <custom>/install.json --postcheck-out <custom>/post.json --report-out <custom>/prepare.json
```

## Low-level commands

For debugging specific steps:

### selfcheck

```bash
python scripts/cuesheet_creator.py selfcheck --json-out <out-dir>/selfcheck.json
```

Purpose:

- Output environment report
- List missing `ffmpeg` / `ffprobe`
- List missing required Python packages
- List missing optional ASR / OCR components
- Suggest next install commands

### install-deps

```bash
python scripts/cuesheet_creator.py install-deps --include-optional none --report-out <out-dir>/install_report.json
python scripts/cuesheet_creator.py install-deps --include-optional scene --report-out <out-dir>/install_report.json
python scripts/cuesheet_creator.py install-deps --include-optional asr --report-out <out-dir>/install_report.json
python scripts/cuesheet_creator.py install-deps --include-optional ocr --report-out <out-dir>/install_report.json
python scripts/cuesheet_creator.py install-deps --include-optional all --report-out <out-dir>/install_report.json
```

Install scope:

- Required: `opencv-python-headless`, `numpy`, `Pillow`, `openpyxl`
- Scene detection: `scenedetect[opencv]` (enhanced cut detection, replaces histogram fallback)
- ASR: `faster-whisper`
- OCR primary: `rapidocr-onnxruntime` (installed by `install-ocr` or `all`)
- OCR alternatives: `easyocr`, `paddleocr` (installed by `install-ocr-extra` or `everything`)

## Mirror & network

For Chinese domestic mirrors:

```bash
python scripts/cuesheet_creator.py prepare-env --mode install-required --out-dir <out-dir> --index-url <mirror>
```

Use cases:

- Default source too slow
- Corporate network restrictions
- Need reliable domestic reachability

## FFmpeg resolution — how cuesheet-creator finds ffmpeg

cuesheet-creator does **not** require ffmpeg on system PATH. It searches in this priority order:

| Priority | Source | How to set |
|---|---|---|
| 1 (highest) | `--ffmpeg-path` / `--ffprobe-path` CLI args | Pass to any command |
| 2 | `CUESHEET_CREATOR_FFMPEG_BIN_DIR` env var | Set for current shell |
| 3 | `<skill-root>/tools/ffmpeg/` portable copy | Extract FFmpeg here (recommended for Windows) |
| 4 | Common OS install locations | Auto-probed: winget, scoop, choco, Homebrew, system paths |
| 5 (lowest) | System PATH | Standard `which` / `where` lookup |

### Windows portable FFmpeg (recommended — zero PATH changes)

1. Download a Windows FFmpeg portable build (for example via `winget install -e --id Gyan.FFmpeg` if package managers are allowed, or by downloading the portable zip manually).
2. Extract it under `<skill-root>/tools/ffmpeg/`.
3. Ensure one of these layouts exists:
   - `<skill-root>/tools/ffmpeg/bin/ffmpeg.exe`
   - `<skill-root>/tools/ffmpeg/<release-folder>/bin/ffmpeg.exe`
4. Re-run:

```bash
python scripts/cuesheet_creator.py prepare-env --mode check-only --out-dir <out-dir>
```

If you must keep FFmpeg outside the skill directory, set a shell-local override first:

```powershell
$env:CUESHEET_CREATOR_FFMPEG_BIN_DIR = "C:\path\to\ffmpeg\bin"
python scripts/cuesheet_creator.py prepare-env --mode check-only --out-dir <out-dir>
```

## Boundaries


### Auto-install WILL handle

- Python packages only
- If `pip` is missing, will try `ensurepip` first
- Post-install re-runs `selfcheck`
- `prepare-env` consolidates pre-check, install results, and post-check

### Auto-install will NOT handle

- Will not modify system PATH
- Will not choose a system package manager for the user

> **FFmpeg auto-download (Windows)**: Use `cuesheet-creator install-ffmpeg` to automatically download the FFmpeg essentials build from gyan.dev with download progress. The binary is extracted to `<skill-root>/tools/ffmpeg/` and auto-detected by all commands. On macOS/Linux, use your package manager instead.

> cuesheet-creator can also use a local portable FFmpeg copy from `<skill-root>/tools/ffmpeg/`, from the shell-local `CUESHEET_CREATOR_FFMPEG_BIN_DIR` override, or via `--ffmpeg-path` / `--ffprobe-path` CLI arguments.


## Recommended execution order

1. Default: run `prepare-env`
2. To only confirm environment: use `--mode check-only`
3. If user allows auto-install: switch to `--mode install-required` / `install-asr` / `install-ocr` / `install-all`
4. Check `prepare_env.json`
5. If issues remain: check `install_report.json` or run `selfcheck` standalone
6. After environment passes: proceed to `scan-video`

## Report key fields

### prepare-env

- `mode`
- `precheck.overall.ready`
- `postcheck.overall.ready`
- `postcheck.overall.blocking`
- `install_report.packages_to_install`
- `install_report.pip_returncode`

### selfcheck

- `overall.ready`
- `overall.blocking`
- `summary.missing_required_packages`
- `summary.missing_external_commands`

### install-deps

- `packages_to_install`
- `pip_command`
- `pip_returncode`
- `postcheck.overall.ready`
- `postcheck.overall.blocking`

## Failure fallback

### `ffmpeg` / `ffprobe` missing

- Stop video analysis — this is a hard gate
- Display auto-detection search results (which locations were probed)
- Provide platform-specific install guidance with copy-paste commands
- Offer three resolution paths: portable copy in `tools/ffmpeg/`, `--ffmpeg-path` CLI override, or system install
- After user installs, re-run `selfcheck` to confirm before proceeding

### pip initialization failure

- Stop auto-install
- Return install report
- Require switching to managed Python or manual fix

### Required Python package install failure

- Retain `prepare_env.json` / `install_report.json`
- Report failed packages and error output to user
- Do not proceed to `scan-video`

### Optional package install failure

- Allow continuing with visual-only version
- Explicitly note ASR / OCR degradation status in subsequent drafts
