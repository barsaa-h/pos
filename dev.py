#!/usr/bin/env python3
"""
dev.py — Developer mode (browser-only, no pywebview needed).
─────────────────────────────────────────────────────────
• Auto-bootstraps venv + deps + DB
• Auto-reloads on Python file changes
• Opens browser automatically
• Ctrl+C to stop

Usage:  ./dev.sh           (first time)
        python3 dev.py     (directly)
"""

import os
import sys
import subprocess
import time
import signal
import urllib.request
import urllib.error

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


def _wait_for_server(port, timeout=15):
    url = f"http://127.0.0.1:{port}/api/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def _open_browser(port):
    url = f"http://127.0.0.1:{port}"
    for browser in ["chromium-browser", "google-chrome", "firefox", "xdg-open"]:
        try:
            subprocess.Popen(
                [browser, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"🌐 Браузер нээгдлээ: {url}")
            return True
        except FileNotFoundError:
            continue
    print(f"🌐 Браузераа нээнэ үү: {url}")
    return False


def _create_dev_shortcut():
    desktop = os.path.expanduser("~/Desktop/МД_Хөгжүүлэлт.desktop")
    icon = os.path.join(PROJECT_DIR, "static", "pos-icon.png")
    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=МД — Хөгжүүлэлт
Name[en]=My Store — Dev Mode
Comment=Хөгжүүлэлтийн горим (auto-reload, браузерт)
Comment[en]=Development mode (auto-reload, browser)
Exec={_venv_python()} {__file__}
Path={PROJECT_DIR}
Icon={icon}
Terminal=false
Categories=Development;
StartupNotify=true
"""
    try:
        if os.path.exists(desktop):
            with open(desktop, "r") as f:
                if content == f.read():
                    return
        with open(desktop, "w") as f:
            f.write(content)
        os.chmod(desktop, 0o755)
        print("✅ Desktop дүрс: МД — Хөгжүүлэлт")
    except Exception as e:
        print(f"⚠️  Desktop дүрс үүсгэхэд алдаа: {e}")


def main():
    _bootstrap()

    port = int(os.environ.get("POS_PORT", "8765"))
    env = os.environ.copy()
    env["POS_DEBUG"] = "1"

    _create_dev_shortcut()

    print("=" * 50)
    print("  МД — Хөгжүүлэлтийн горим")
    print("=" * 50)
    print(f"  URL:    http://127.0.0.1:{port}")
    print("  Reload: Python файл хадгалахад автомат")
    print("  Зогсоох: Ctrl+C")
    print()

    flask_proc = subprocess.Popen(
        [
            sys.executable, "-m", "flask",
            "--app", "app:app",
            "run",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--reload",
        ],
        cwd=PROJECT_DIR,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
        preexec_fn=os.setsid if sys.platform != "win32" else None,
    )

    def _forward_signal(signum, frame):
        if flask_proc.poll() is None:
            if sys.platform == "win32":
                flask_proc.terminate()
            else:
                os.killpg(os.getpgid(flask_proc.pid), signum)

    signal.signal(signal.SIGINT, _forward_signal)
    signal.signal(signal.SIGTERM, _forward_signal)

    if _wait_for_server(port):
        _open_browser(port)
    else:
        print(f"⚠️  Сервер {port} портонд ачаалсангүй (15s timeout)", file=sys.stderr)

    try:
        flask_proc.wait()
    except KeyboardInterrupt:
        pass

    if flask_proc.poll() is None:
        if sys.platform == "win32":
            flask_proc.terminate()
        else:
            os.killpg(os.getpgid(flask_proc.pid), signal.SIGTERM)
        flask_proc.wait()

    print("\n🛑 Хөгжүүлэлтийн сервер зогслоо")


if __name__ == "__main__":
    main()
