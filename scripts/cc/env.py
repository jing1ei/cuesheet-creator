"""Environment detection, selfcheck, dependency installation."""
from __future__ import annotations

from cuesheet_creator import (
    _common_ffmpeg_dirs,
    build_pip_install_command,
    check_command,
    check_module,
    cmd_install_deps,
    cmd_prepare_env,
    cmd_selfcheck,
    collect_missing_python_packages,
    ensure_pip_available,
    ffmpeg_install_hints,
    iter_local_ffmpeg_bin_dirs,
    load_requirements_constraints,
    make_selfcheck_report,
    normalize_optional_groups,
    print_install_report,
    print_prepare_env_report,
    print_selfcheck_text,
    resolve_command_path,
    resolve_prepare_env_output_paths,
    resolve_prepare_mode,
    run_install_deps_flow,
    stringify_output_paths,
    summarize_report,
)

__all__ = ['_common_ffmpeg_dirs', 'iter_local_ffmpeg_bin_dirs', 'resolve_command_path', 'ffmpeg_install_hints', 'normalize_optional_groups', 'check_command', 'check_module', 'summarize_report', 'make_selfcheck_report', 'print_selfcheck_text', 'cmd_selfcheck', 'collect_missing_python_packages', 'ensure_pip_available', 'load_requirements_constraints', 'build_pip_install_command', 'print_install_report', 'run_install_deps_flow', 'cmd_install_deps', 'resolve_prepare_mode', 'resolve_prepare_env_output_paths', 'stringify_output_paths', 'print_prepare_env_report', 'cmd_prepare_env']
