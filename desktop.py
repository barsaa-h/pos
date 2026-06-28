#!/usr/bin/env python3
"""
POS Desktop Launcher — self-bootstrapping, no setup needed.
Run:  python3 desktop.py          (auto-bootstraps venv + deps + DB)
      python3 desktop.py --dev    (dev mode: Flask auto-reload)
      ./start.sh                  (shell wrapper, for .desktop files)

Platform dispatch order on Linux:
  1. mint/  — Linux Mint XFCE (store computers, optimized for i5 2nd gen)
  2. ubuntu/ — Ubuntu / generic Linux
"""

import sys
import os
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _is_venv():
    return (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )


def _venv_python():
    if sys.platform == "win32":
        return os.path.join(PROJECT_DIR, "venv", "Scripts", "python.exe")
    return os.path.join(PROJECT_DIR, "venv", "bin", "python3")


def _ensure_venv():
    vp = _venv_python()
    if not os.path.exists(vp):
        print("📦 Виртуал орчин үүсгэж байна...")
        subprocess.run(
            [sys.executable, "-m", "venv", os.path.join(PROJECT_DIR, "venv")],
            check=True,
        )
    return vp


def _ensure_dependencies():
    try:
        import flask  # noqa: F401
        import webview  # noqa: F401
    except ImportError:
        print("📦 Хамаарлууд суулгаж байна...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "-q"],
            check=True,
        )
        subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "-r", os.path.join(PROJECT_DIR, "requirements.txt"), "-q",
            ],
            check=True,
        )


def _ensure_directories():
    for d in ["logs", "backups", os.path.join("static", "uploads")]:
        os.makedirs(os.path.join(PROJECT_DIR, d), exist_ok=True)


def _ensure_database():
    db_path = os.environ.get("POS_DB_PATH", os.path.join(PROJECT_DIR, "pos.db"))
    if not os.path.exists(db_path):
        import database as db
        db.init_db()


def _bootstrap():
    os.chdir(PROJECT_DIR)
    sys.path.insert(0, PROJECT_DIR)

    if not _is_venv():
        vp = _ensure_venv()
        args = [vp, __file__] + sys.argv[1:]
        if sys.platform == "win32":
            os.execv(vp, args)
        else:
            os.execv(vp, args)
        sys.exit(0)

    _ensure_directories()
    _ensure_dependencies()
    _ensure_database()


def _detect_linux_flavor():
    """Return the platform-specific launcher directory on Linux.

    Detection order:
      1. POS_LAUNCHER env var override (for tests/CI)
      2. /etc/os-release → prefer mint/ if ID or ID_LIKE is linuxmint
      3. Fall back to ubuntu/
    """
    override = os.environ.get("POS_LAUNCHER", "").strip()
    if override in ("mint", "ubuntu"):
        return override

    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            data = f.read().lower()
        if "linuxmint" in data or "linux mint" in data:
            return "mint"
    except OSError:
        pass

    return "ubuntu"


def main():
    _bootstrap()

    import platform
    import runpy

    system = platform.system()
    if system == "Windows":
        entry = os.path.join(PROJECT_DIR, "windows", "desktop.py")
    elif system == "Linux":
        flavor = _detect_linux_flavor()
        entry = os.path.join(PROJECT_DIR, flavor, "desktop.py")
        # Final fallback to ubuntu/ if mint/ doesn't exist for some reason
        if not os.path.exists(entry):
            entry = os.path.join(PROJECT_DIR, "ubuntu", "desktop.py")
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(entry):
        print(f"Platform launcher not found: {entry}", file=sys.stderr)
        sys.exit(1)

    runpy.run_path(entry, run_name="__main__")


if __name__ == "__main__":
    main()
