"""Environment detection, selfcheck, dependency installation."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from cc.constants import (
    _CLI_COMMAND_OVERRIDES,
    LOCAL_FFMPEG_BIN_ENV,
    LOCAL_FFMPEG_SEARCH_ROOT,
    OPTIONAL_COMPONENTS,
    PREPARE_ENV_DEFAULT_FILES,
    PREPARE_ENV_MODES,
    REQUIRED_PACKAGES,
    SUPPORTED_OPTIONAL_GROUPS,
)
from cc.utils import (
    command_filename,
    detect_platform_family,
    run_command,
    truncate_text,
    unique_in_order,
    write_json,
)

# ---------------------------------------------------------------------------
# FFmpeg discovery
# ---------------------------------------------------------------------------

def _common_ffmpeg_dirs() -> list[tuple[Path, str]]:
    """Return platform-specific common FFmpeg install locations."""
    family = detect_platform_family()
    dirs: list[tuple[Path, str]] = []
    if family == "windows":
        local_app = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
        if local_app.exists():
            dirs.append((local_app, "winget"))
        scoop_root = Path(os.environ.get("SCOOP", Path.home() / "scoop"))
        dirs.append((scoop_root / "shims", "scoop"))
        dirs.append((scoop_root / "apps" / "ffmpeg" / "current" / "bin", "scoop"))
        choco_root = Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey"))
        dirs.append((choco_root / "bin", "choco"))
        for drive in ("C:", "D:"):
            dirs.append((Path(drive) / "ffmpeg" / "bin", "manual"))
            dirs.append((Path(drive) / "tools" / "ffmpeg" / "bin", "manual"))
        prog = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        dirs.append((prog / "ffmpeg" / "bin", "programfiles"))
    elif family == "macos":
        dirs.append((Path("/opt/homebrew/bin"), "homebrew-arm"))
        dirs.append((Path("/usr/local/bin"), "homebrew-intel"))
        dirs.append((Path("/opt/local/bin"), "macports"))
    else:
        dirs.append((Path("/usr/bin"), "system"))
        dirs.append((Path("/usr/local/bin"), "local"))
        dirs.append((Path("/snap/bin"), "snap"))
    return dirs


def iter_local_ffmpeg_bin_dirs() -> list[tuple[Path, str]]:
    """Ordered list of directories to search for ffmpeg/ffprobe."""
    candidates: list[tuple[Path, str]] = []
    seen: set[str] = set()

    def add(path: Path | None, source: str) -> None:
        if path is None:
            return
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            return
        seen.add(key)
        candidates.append((path, source))

    env_value = os.environ.get(LOCAL_FFMPEG_BIN_ENV, "").strip()
    if env_value:
        add(Path(env_value).expanduser(), f"env:{LOCAL_FFMPEG_BIN_ENV}")

    add(LOCAL_FFMPEG_SEARCH_ROOT / "bin", "local-tools")
    add(LOCAL_FFMPEG_SEARCH_ROOT, "local-tools")
    if LOCAL_FFMPEG_SEARCH_ROOT.exists():
        for child in sorted(LOCAL_FFMPEG_SEARCH_ROOT.iterdir(), key=lambda item: item.name.lower()):
            if child.is_dir():
                add(child / "bin", f"local-tools:{child.name}")
                add(child, f"local-tools:{child.name}")

    for common_dir, source in _common_ffmpeg_dirs():
        add(common_dir, source)

    return candidates


def resolve_command_path(name: str) -> tuple[str | None, str | None]:
    """Resolve path for an external command."""
    cli_override = _CLI_COMMAND_OVERRIDES.get(name)
    if cli_override:
        p = Path(cli_override)
        if p.exists() and p.is_file():
            return str(p.resolve()), "cli-override"
        print(f"WARNING: --{name}-path was set to '{cli_override}' but that file does not exist. Falling back to auto-detection.", file=sys.stderr)

    executable = command_filename(name)
    for bin_dir, source in iter_local_ffmpeg_bin_dirs():
        candidate = bin_dir / executable
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve()), source
    path = shutil.which(name)
    if path:
        return path, "PATH"
    return None, None


def ffmpeg_install_hints() -> dict[str, Any]:
    """Return structured install hints."""
    family = detect_platform_family()
    if family == "windows":
        return {
            "primary": "Download FFmpeg from https://www.gyan.dev/ffmpeg/builds/ (essentials build zip). Extract to <skill-root>/tools/ffmpeg/ so it contains <release-folder>/bin/ffmpeg.exe. No PATH changes needed — cuesheet-creator auto-detects it.",
            "fallbacks": [
                "If portable placement didn't work: check that <skill-root>/tools/ffmpeg/ contains either bin/ffmpeg.exe directly or <release-folder>/bin/ffmpeg.exe one level down.",
                "Alternative: install via winget (`winget install Gyan.FFmpeg`), scoop, or choco. After install, close and reopen your PowerShell window, then re-check.",
                f"Direct override: pass `--ffmpeg-path <path> --ffprobe-path <path>` to any command, or set {LOCAL_FFMPEG_BIN_ENV}=<directory>.",
            ],
        }
    if family == "macos":
        return {
            "primary": "Run `brew install ffmpeg` in Terminal. cuesheet-creator auto-detects /opt/homebrew/bin and /usr/local/bin.",
            "fallbacks": [
                "If brew install succeeded but selfcheck still shows MISSING: close and reopen your Terminal window, then re-check.",
                "Alternative: extract FFmpeg binaries into <skill-root>/tools/ffmpeg/bin/.",
                "Direct override: pass `--ffmpeg-path` / `--ffprobe-path` to any command.",
            ],
        }
    return {
        "primary": "Install via package manager: `sudo apt install ffmpeg` (or your distro's equivalent).",
        "fallbacks": [
            "If install succeeded but selfcheck still shows MISSING: close and reopen your terminal, then re-check.",
            "Alternative: extract FFmpeg binaries into <skill-root>/tools/ffmpeg/bin/.",
            "Direct override: pass `--ffmpeg-path` / `--ffprobe-path` to any command.",
        ],
    }


# ---------------------------------------------------------------------------
# Package & module checks
# ---------------------------------------------------------------------------

def normalize_optional_groups(value: str | None) -> set[str]:
    if not value:
        return set()
    raw = value.strip().lower()
    if raw in {"", "none"}:
        return set()
    groups: set[str] = set()
    for part in raw.split(","):
        item = part.strip()
        if not item or item == "none":
            continue
        if item == "all":
            return set(SUPPORTED_OPTIONAL_GROUPS)
        if item not in SUPPORTED_OPTIONAL_GROUPS:
            valid = ", ".join(sorted(SUPPORTED_OPTIONAL_GROUPS | {"all", "none"}))
            raise ValueError(f"Unknown optional group: {item}, valid values: {valid}")
        groups.add(item)
    return groups


def check_command(name: str) -> dict[str, Any]:
    path, source = resolve_command_path(name)
    result: dict[str, Any] = {
        "name": name,
        "available": bool(path),
        "path": path,
        "source": source,
        "version": None,
    }
    if not path:
        return result
    completed = run_command([path, "-version"])
    text = (completed.stdout or completed.stderr or "").strip().splitlines()
    result["version"] = text[0] if text else None
    return result


def check_module(package_name: str, import_name: str, pip_name: str | None = None, pip_spec: str | None = None, group: str | None = None) -> dict[str, Any]:
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", None)
        return {
            "package": package_name,
            "pip_name": pip_name or package_name,
            "pip_spec": pip_spec or pip_name or package_name,
            "group": group,
            "import": import_name,
            "available": True,
            "installed_version": version,
        }
    except Exception as exc:
        return {
            "package": package_name,
            "pip_name": pip_name or package_name,
            "pip_spec": pip_spec or pip_name or package_name,
            "group": group,
            "import": import_name,
            "available": False,
            "installed_version": None,
            "error": str(exc),
        }


def summarize_report(required_packages: dict[str, Any], optional_components: dict[str, Any], ffmpeg: dict[str, Any], ffprobe: dict[str, Any]) -> dict[str, Any]:
    missing_required_packages = [package for package, info in required_packages.items() if not info["available"]]
    missing_optional_components = [name for name, info in optional_components.items() if not info["available"]]
    missing_external_commands = []
    if not ffmpeg["available"]:
        missing_external_commands.append("ffmpeg")
    if not ffprobe["available"]:
        missing_external_commands.append("ffprobe")
    return {
        "missing_required_packages": missing_required_packages,
        "missing_optional_components": missing_optional_components,
        "missing_external_commands": missing_external_commands,
    }


# ---------------------------------------------------------------------------
# Selfcheck
# ---------------------------------------------------------------------------

def make_selfcheck_report() -> dict[str, Any]:
    required_packages = {
        package: check_module(package, import_name, pip_name=package)
        for package, import_name in REQUIRED_PACKAGES.items()
    }
    optional_components = {
        name: check_module(
            package_name=name,
            import_name=meta["import_name"],
            pip_name=meta["pip_name"],
            pip_spec=meta.get("pip_spec"),
            group=meta["group"],
        )
        for name, meta in OPTIONAL_COMPONENTS.items()
    }

    ffmpeg = check_command("ffmpeg")
    ffprobe = check_command("ffprobe")

    blocking: list[str] = []
    warnings: list[str] = []

    if sys.version_info < (3, 10):
        blocking.append("Python version below 3.10")

    if not ffmpeg["available"]:
        blocking.append("Missing ffmpeg")
    if not ffprobe["available"]:
        blocking.append("Missing ffprobe")

    for package, item in required_packages.items():
        if not item["available"]:
            blocking.append(f"Missing required Python package: {package}")

    for name, item in optional_components.items():
        if not item["available"] and item.get("group") != "ocr-extra":
            warnings.append(f"Optional component unavailable: {name}")

    summary = summarize_report(required_packages, optional_components, ffmpeg, ffprobe)

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "python": {
            "available": True,
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "ok": sys.version_info >= (3, 10),
        },
        "commands": {
            "ffmpeg": ffmpeg,
            "ffprobe": ffprobe,
        },
        "required_packages": required_packages,
        "optional_components": optional_components,
        "summary": summary,
        "install_options": {
            "check_only": "python scripts/cuesheet_creator.py selfcheck --json-out <out-dir>/selfcheck.json",
            "install_required": "python scripts/cuesheet_creator.py install-deps --include-optional none --report-out <out-dir>/install_report.json",
            "install_with_scene": "python scripts/cuesheet_creator.py install-deps --include-optional scene --report-out <out-dir>/install_report.json",
            "install_with_asr": "python scripts/cuesheet_creator.py install-deps --include-optional asr --report-out <out-dir>/install_report.json",
            "install_with_ocr": "python scripts/cuesheet_creator.py install-deps --include-optional ocr --report-out <out-dir>/install_report.json",
            "install_with_all_optional": "python scripts/cuesheet_creator.py install-deps --include-optional all --report-out <out-dir>/install_report.json",
            "prepare_check_only": "python scripts/cuesheet_creator.py prepare-env --mode check-only --out-dir <out-dir>",
            "prepare_install_required": "python scripts/cuesheet_creator.py prepare-env --mode install-required --out-dir <out-dir>",
            "prepare_install_scene": "python scripts/cuesheet_creator.py prepare-env --mode install-scene --out-dir <out-dir>",
            "prepare_install_asr": "python scripts/cuesheet_creator.py prepare-env --mode install-asr --out-dir <out-dir>",
            "prepare_install_ocr": "python scripts/cuesheet_creator.py prepare-env --mode install-ocr --out-dir <out-dir>",
            "prepare_install_all": "python scripts/cuesheet_creator.py prepare-env --mode install-all --out-dir <out-dir>",
        },
        "guidance": {
            "ffmpeg_install_hints": ffmpeg_install_hints(),
            "local_ffmpeg_search_root": str(LOCAL_FFMPEG_SEARCH_ROOT),
            "local_ffmpeg_bin_env": LOCAL_FFMPEG_BIN_ENV,
            "python_package_policy": [
                "Only run install-deps when the user explicitly allows auto-install.",
                "Prefer installing in isolated or managed Python environments.",
                "install-deps only handles Python packages; it does not auto-install ffmpeg/ffprobe.",
            ],
        },
        "overall": {
            "ready": len(blocking) == 0,
            "blocking": blocking,
            "warnings": warnings,
        },
    }


def print_selfcheck_text(report: dict[str, Any]) -> None:
    print("=== cuesheet-creator selfcheck ===")
    print(f"Python: {report['python']['version']} @ {report['python']['executable']}")
    ffmpeg_state = report["commands"]["ffmpeg"]
    ffprobe_state = report["commands"]["ffprobe"]
    print(f"ffmpeg : {'OK' if ffmpeg_state['available'] else 'MISSING'}" + (f" [{ffmpeg_state.get('source')}]" if ffmpeg_state.get('source') else ""))
    if ffmpeg_state.get("path"):
        print(f"         {ffmpeg_state['path']}")
    print(f"ffprobe: {'OK' if ffprobe_state['available'] else 'MISSING'}" + (f" [{ffprobe_state.get('source')}]" if ffprobe_state.get('source') else ""))
    if ffprobe_state.get("path"):
        print(f"         {ffprobe_state['path']}")
    print("Required packages:")
    for package, info in report["required_packages"].items():
        state = "OK" if info["available"] else "MISSING"
        version = info.get("installed_version") or "unknown"
        print(f"  - {package}: {state} ({version})")
    print("Optional components:")
    for name, info in report["optional_components"].items():
        state = "OK" if info["available"] else "UNAVAILABLE"
        version = info.get("installed_version") or "unknown"
        group = info.get("group") or "optional"
        print(f"  - {name} [{group}]: {state} ({version})")
    if report["overall"]["blocking"]:
        print("Blocking issues:")
        for item in report["overall"]["blocking"]:
            print(f"  - {item}")
    if report["overall"]["warnings"]:
        print("Warnings:")
        for item in report["overall"]["warnings"]:
            print(f"  - {item}")
    if report["summary"]["missing_external_commands"]:
        print("ffmpeg guidance:")
        print(f"  - local search root: {report['guidance']['local_ffmpeg_search_root']}")
        print(f"  - override env    : {report['guidance']['local_ffmpeg_bin_env']}")
        hints = report["guidance"]["ffmpeg_install_hints"]
        print(f"  - (primary) {hints['primary']}")
        for fb in hints.get("fallbacks", []):
            print(f"  - (fallback) {fb}")
    print("Install flow:")
    print(f"  - only selfcheck : {report['install_options']['check_only']}")
    print(f"  - auto required  : {report['install_options']['install_required']}")
    print(f"  - + scene detect : {report['install_options']['install_with_scene']}")
    print(f"  - + ASR optional : {report['install_options']['install_with_asr']}")
    print(f"  - + OCR optional : {report['install_options']['install_with_ocr']}")
    print(f"  - + all optional : {report['install_options']['install_with_all_optional']}")
    print("One-command flow:")
    print(f"  - check only     : {report['install_options']['prepare_check_only']}")
    print(f"  - install needed : {report['install_options']['prepare_install_required']}")
    print(f"  - + scene detect : {report['install_options']['prepare_install_scene']}")
    print(f"  - + ASR optional : {report['install_options']['prepare_install_asr']}")
    print(f"  - + OCR optional : {report['install_options']['prepare_install_ocr']}")
    print(f"  - install all    : {report['install_options']['prepare_install_all']}")
    print(f"Ready: {'YES' if report['overall']['ready'] else 'NO'}")


def cmd_selfcheck(args: argparse.Namespace) -> int:
    report = make_selfcheck_report()
    if args.json_out:
        write_json(Path(args.json_out), report)
    if args.output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_selfcheck_text(report)
    if args.fail_on_missing_required and not report["overall"]["ready"]:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Install deps
# ---------------------------------------------------------------------------

def collect_missing_python_packages(report: dict[str, Any], optional_groups: set[str]) -> list[str]:
    packages = [
        info.get("pip_spec") or info["pip_name"]
        for info in report["required_packages"].values()
        if not info["available"]
    ]
    for info in report["optional_components"].values():
        if info["available"]:
            continue
        if info.get("group") in optional_groups:
            packages.append(info.get("pip_spec") or info["pip_name"])
    return unique_in_order(packages)


def ensure_pip_available(python_executable: str) -> tuple[bool, list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    check_cmd = [python_executable, "-m", "pip", "--version"]
    check_result = run_command(check_cmd)
    steps.append({
        "step": "check-pip",
        "command": check_cmd,
        "returncode": check_result.returncode,
        "stdout": truncate_text(check_result.stdout),
        "stderr": truncate_text(check_result.stderr),
    })
    if check_result.returncode == 0:
        return True, steps
    ensure_cmd = [python_executable, "-m", "ensurepip", "--upgrade"]
    ensure_result = run_command(ensure_cmd)
    steps.append({
        "step": "ensurepip",
        "command": ensure_cmd,
        "returncode": ensure_result.returncode,
        "stdout": truncate_text(ensure_result.stdout),
        "stderr": truncate_text(ensure_result.stderr),
    })
    recheck_result = run_command(check_cmd)
    steps.append({
        "step": "recheck-pip",
        "command": check_cmd,
        "returncode": recheck_result.returncode,
        "stdout": truncate_text(recheck_result.stdout),
        "stderr": truncate_text(recheck_result.stderr),
    })
    return recheck_result.returncode == 0, steps


def load_requirements_constraints() -> dict[str, str]:
    """Parse requirements.txt and return {bare_package_name: 'name>=x,<y'}."""
    from cc.constants import SKILL_ROOT
    req_path = SKILL_ROOT / "requirements.txt"
    constraints: dict[str, str] = {}
    if not req_path.exists():
        return constraints
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bare = line.split(">=")[0].split("<=")[0].split("==")[0].split("<")[0].split(">")[0].split("[")[0].strip()
        if bare:
            constraints[bare.lower()] = line
    return constraints


def build_pip_install_command(args: argparse.Namespace, packages: list[str]) -> list[str]:
    constraints = load_requirements_constraints()
    resolved: list[str] = []
    for pkg in packages:
        bare = pkg.split(">=")[0].split("[")[0].strip().lower()
        if bare in constraints:
            resolved.append(constraints[bare])
        else:
            resolved.append(pkg)
    command = [sys.executable, "-m", "pip", "install"]
    if args.upgrade_pip:
        command.extend(["--upgrade", "pip"])
    command.extend(resolved)
    if args.index_url:
        command.extend(["--index-url", args.index_url])
    if args.extra_index_url:
        command.extend(["--extra-index-url", args.extra_index_url])
    return command


def print_install_report(report: dict[str, Any]) -> None:
    print("=== cuesheet-creator install-deps ===")
    print(f"Python: {report['python_executable']}")
    print(f"Optional groups: {', '.join(report['optional_groups']) if report['optional_groups'] else 'none'}")
    print(f"Dry run: {'YES' if report['dry_run'] else 'NO'}")
    print(f"Packages selected: {', '.join(report['packages_to_install']) if report['packages_to_install'] else '(none)'}")
    if report["precheck"]["summary"]["missing_external_commands"]:
        print("External blockers still require manual install:")
        for item in report["precheck"]["summary"]["missing_external_commands"]:
            print(f"  - {item}")
        hints = report["precheck"]["guidance"]["ffmpeg_install_hints"]
        print(f"  - (primary) {hints['primary']}")
        for fb in hints.get("fallbacks", []):
            print(f"  - (fallback) {fb}")
    if report.get("pip_bootstrap_steps"):
        print("pip bootstrap steps:")
        for step in report["pip_bootstrap_steps"]:
            print(f"  - {step['step']}: rc={step['returncode']}")
    if report.get("pip_command"):
        print("Install command:")
        print("  " + " ".join(report["pip_command"]))
    if report.get("pip_returncode") is not None:
        print(f"pip returncode: {report['pip_returncode']}")
    if report.get("pip_stdout"):
        print("pip stdout:")
        print(report["pip_stdout"])
    if report.get("pip_stderr"):
        print("pip stderr:")
        print(report["pip_stderr"])
    print(f"Ready after install: {'YES' if report['postcheck']['overall']['ready'] else 'NO'}")
    if report["postcheck"]["overall"]["blocking"]:
        print("Remaining blocking issues:")
        for item in report["postcheck"]["overall"]["blocking"]:
            print(f"  - {item}")


def run_install_deps_flow(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    optional_groups = normalize_optional_groups(args.include_optional)
    precheck = make_selfcheck_report()
    packages_to_install = collect_missing_python_packages(precheck, optional_groups)

    report: dict[str, Any] = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "python_executable": sys.executable,
        "optional_groups": sorted(optional_groups),
        "dry_run": bool(args.dry_run),
        "precheck": precheck,
        "packages_to_install": packages_to_install,
        "pip_bootstrap_steps": [],
        "pip_command": None,
        "pip_returncode": None,
        "pip_stdout": "",
        "pip_stderr": "",
        "postcheck": precheck,
    }

    if not packages_to_install:
        return 0, report

    pip_ready, pip_bootstrap_steps = ensure_pip_available(sys.executable)
    report["pip_bootstrap_steps"] = pip_bootstrap_steps
    if not pip_ready:
        report["pip_stderr"] = "Unable to initialize pip. Please check the current Python environment."
        return 1, report

    pip_command = build_pip_install_command(args, packages_to_install)
    report["pip_command"] = pip_command

    if not args.dry_run:
        install_result = run_command(pip_command)
        report["pip_returncode"] = install_result.returncode
        report["pip_stdout"] = truncate_text(install_result.stdout, limit=12000)
        report["pip_stderr"] = truncate_text(install_result.stderr, limit=12000)
        report["postcheck"] = make_selfcheck_report()
    else:
        report["postcheck"] = precheck

    if args.dry_run:
        return 0, report
    if report["pip_returncode"] not in (0, None):
        return 1, report
    return 0, report


def cmd_install_deps(args: argparse.Namespace) -> int:
    exit_code, report = run_install_deps_flow(args)
    if args.report_out:
        write_json(Path(args.report_out), report)
    if args.output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_install_report(report)
    if exit_code != 0:
        return exit_code
    if args.fail_on_blocking and not report["postcheck"]["overall"]["ready"]:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Prepare-env
# ---------------------------------------------------------------------------

def resolve_prepare_mode(mode: str) -> set[str]:
    if mode not in PREPARE_ENV_MODES:
        valid = ", ".join(sorted(PREPARE_ENV_MODES))
        raise ValueError(f"Unknown prepare mode: {mode}, valid values: {valid}")
    return set(PREPARE_ENV_MODES[mode])


def resolve_prepare_env_output_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    out_dir = Path(args.out_dir).resolve() if args.out_dir else None

    def pick(explicit_value: str | None, default_name: str) -> Path | None:
        if explicit_value:
            return Path(explicit_value)
        if out_dir is not None:
            return out_dir / default_name
        return None

    return {
        "out_dir": out_dir,
        "precheck": pick(args.selfcheck_out, PREPARE_ENV_DEFAULT_FILES["precheck"]),
        "install_report": pick(args.install_report_out, PREPARE_ENV_DEFAULT_FILES["install_report"]),
        "postcheck": pick(args.postcheck_out, PREPARE_ENV_DEFAULT_FILES["postcheck"]),
        "report": pick(args.report_out, PREPARE_ENV_DEFAULT_FILES["report"]),
    }


def stringify_output_paths(paths: dict[str, Path | None]) -> dict[str, str | None]:
    return {
        key: (str(value) if isinstance(value, Path) else None)
        for key, value in paths.items()
        if key != "out_dir"
    }


def print_prepare_env_report(report: dict[str, Any]) -> None:
    print("=== cuesheet-creator prepare-env ===")
    print(f"Mode: {report['mode']}")
    print(f"Dry run: {'YES' if report['dry_run'] else 'NO'}")
    if report.get("output_directory"):
        print(f"Output directory: {report['output_directory']}")
    if report.get("output_files"):
        print("Output files:")
        for key, value in report["output_files"].items():
            if value:
                print(f"  - {key}: {value}")
    print(f"Precheck ready : {'YES' if report['precheck']['overall']['ready'] else 'NO'}")
    if report["precheck"]["overall"]["blocking"]:
        print("Precheck blocking issues:")
        for item in report["precheck"]["overall"]["blocking"]:
            print(f"  - {item}")
    if report["install_invoked"]:
        print("Install step: EXECUTED")
        install_report = report.get("install_report") or {}
        packages = install_report.get("packages_to_install") or []
        print(f"  Packages selected: {', '.join(packages) if packages else '(none)'}")
        if install_report.get("pip_command"):
            print("  Install command:")
            print("    " + " ".join(install_report["pip_command"]))
        if install_report.get("pip_returncode") is not None:
            print(f"  pip returncode: {install_report['pip_returncode']}")
    else:
        print("Install step: SKIPPED")
    print(f"Postcheck ready: {'YES' if report['postcheck']['overall']['ready'] else 'NO'}")
    if report["postcheck"]["overall"]["blocking"]:
        print("Postcheck blocking issues:")
        for item in report["postcheck"]["overall"]["blocking"]:
            print(f"  - {item}")
    if report["postcheck"]["summary"]["missing_external_commands"]:
        print("External commands still need manual install:")
        for item in report["postcheck"]["summary"]["missing_external_commands"]:
            print(f"  - {item}")
        print(f"  - local search root: {report['postcheck']['guidance']['local_ffmpeg_search_root']}")
        print(f"  - override env    : {report['postcheck']['guidance']['local_ffmpeg_bin_env']}")
        hints = report["postcheck"]["guidance"]["ffmpeg_install_hints"]
        print(f"  - (primary) {hints['primary']}")
        for fb in hints.get("fallbacks", []):
            print(f"  - (fallback) {fb}")


def cmd_prepare_env(args: argparse.Namespace) -> int:
    optional_groups = resolve_prepare_mode(args.mode)
    output_paths = resolve_prepare_env_output_paths(args)
    precheck = make_selfcheck_report()
    if output_paths["precheck"]:
        write_json(output_paths["precheck"], precheck)

    output_files = stringify_output_paths(output_paths)
    if args.mode == "check-only":
        output_files["install_report"] = None

    report: dict[str, Any] = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": args.mode,
        "optional_groups": sorted(optional_groups),
        "dry_run": bool(args.dry_run),
        "output_directory": str(output_paths["out_dir"]) if output_paths["out_dir"] else None,
        "output_files": output_files,
        "precheck": precheck,
        "install_invoked": False,
        "install_report": None,
        "postcheck": precheck,
    }

    exit_code = 0
    if args.mode != "check-only":
        install_args = argparse.Namespace(
            include_optional="none" if not optional_groups else ",".join(sorted(optional_groups)),
            dry_run=args.dry_run,
            report_out=None,
            output_format="json",
            index_url=args.index_url,
            extra_index_url=args.extra_index_url,
            upgrade_pip=args.upgrade_pip,
            fail_on_blocking=False,
        )
        install_exit_code, install_report = run_install_deps_flow(install_args)
        report["install_invoked"] = True
        report["install_report"] = install_report
        exit_code = install_exit_code
        if output_paths["install_report"]:
            write_json(output_paths["install_report"], install_report)
        if not args.dry_run:
            report["postcheck"] = make_selfcheck_report()
        else:
            report["postcheck"] = precheck
    else:
        report["postcheck"] = precheck

    if output_paths["postcheck"]:
        write_json(output_paths["postcheck"], report["postcheck"])
    if output_paths["report"]:
        write_json(output_paths["report"], report)

    if args.output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_prepare_env_report(report)

    if exit_code != 0:
        return exit_code
    if args.fail_on_blocking and not report["postcheck"]["overall"]["ready"]:
        return 1
    return 0


__all__ = [
    "_common_ffmpeg_dirs",
    "iter_local_ffmpeg_bin_dirs",
    "resolve_command_path",
    "ffmpeg_install_hints",
    "normalize_optional_groups",
    "check_command",
    "check_module",
    "summarize_report",
    "make_selfcheck_report",
    "print_selfcheck_text",
    "cmd_selfcheck",
    "collect_missing_python_packages",
    "ensure_pip_available",
    "load_requirements_constraints",
    "build_pip_install_command",
    "print_install_report",
    "run_install_deps_flow",
    "cmd_install_deps",
    "resolve_prepare_mode",
    "resolve_prepare_env_output_paths",
    "stringify_output_paths",
    "print_prepare_env_report",
    "cmd_prepare_env",
]
