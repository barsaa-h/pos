"""
Ubuntu Desktop Launcher for POS System.
Double-click .desktop icon or run: python3 ubuntu/desktop.py

Optimized for Ubuntu:
- GTK backend via pywebview
- /dev/usb/lp* auto-detection for thermal printers
- flock-based single-instance lock
- systemd service support
- XDG desktop integration
"""

import sys
import os
import threading
import time
import logging
import argparse
import socket
import platform
import tempfile
import fcntl

assert platform.system() == "Linux", "This launcher is for Linux only"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PROJECT_DIR)
sys.path.insert(0, ROOT_DIR)

FLASK_PORT = int(os.environ.get("POS_PORT", "8765"))
DEV_MODE = "--dev" in sys.argv
LOCK_FILE = os.path.join(tempfile.gettempdir(), "pos-app-ubuntu.lock")

# File logging for production debugging
os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(ROOT_DIR, "logs", "pos.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

_lock_fd = None


def acquire_lock():
    """Linux: flock with PID validation to handle stale locks."""
    global _lock_fd
    try:
        _lock_fd = open(LOCK_FILE, "w")
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_fd.write(str(os.getpid()))
            _lock_fd.flush()
            return True
        except (IOError, OSError):
            # Lock held - check if holder PID is alive
            try:
                with open(LOCK_FILE, "r") as f:
                    old_pid = f.read().strip()
                if old_pid:
                    os.kill(int(old_pid), 0)  # Signal 0 = check if alive
                    return False  # PID alive, legit lock
            except (OSError, ValueError):
                logger.warning("Unhandled exception in: except (OSError, ValueError):")
                pass
            # Stale lock - force acquire
            _lock_fd.close()
            os.remove(LOCK_FILE)
            _lock_fd = open(LOCK_FILE, "w")
            fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_fd.write(str(os.getpid()))
            _lock_fd.flush()
            return True
    except Exception:
        return False


def release_lock():
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except Exception:
            logger.warning("Unhandled exception in: except Exception:")
            pass
        _lock_fd = None
    try:
        os.remove(LOCK_FILE)
    except Exception:
        logger.warning("Unhandled exception in: except Exception:")
        pass
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except socket.error:
            return False


def run_flask(port):
    # Avoid double-init: importing app triggers _application = create_app()
    # at module level, which would spawn GC/checkpoint/heartbeat threads twice
    # and double the eBarimt retry cost. ~150ms saved on slow hardware.
    os.environ.setdefault("POS_SKIP_MODULE_INIT", "1")
    from app import create_app
    app = create_app()
    app.run(
        host="127.0.0.1",
        port=port,
        debug=DEV_MODE,
        use_reloader=DEV_MODE,
        extra_files=[
            os.path.join(ROOT_DIR, "templates"),
            os.path.join(ROOT_DIR, "static"),
        ] if DEV_MODE else None,
    )


def wait_for_server(port, timeout=15):
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def get_secondary_monitor():
    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
        if len(monitors) >= 2:
            for m in monitors:
                if not getattr(m, "is_primary", False):
                    return (m.x, m.y, m.width, m.height)
            if len(monitors) >= 2:
                m = monitors[1]
                return (m.x, m.y, m.width, m.height)
    except Exception as e:
        logger.warning(f"Could not detect secondary monitor: {e}")
    return None


_splash_root = None


def show_splash():
    global _splash_root
    try:
        import tkinter as tk
        from tkinter import font
        _splash_root = tk.Tk()
        _splash_root.overrideredirect(True)
        _splash_root.attributes("-topmost", True)
        ws = _splash_root.winfo_screenwidth()
        hs = _splash_root.winfo_screenheight()
        w, h = 400, 230
        x, y = (ws - w) // 2, (hs - h) // 2
        _splash_root.geometry(f"{w}x{h}+{x}+{y}")
        _splash_root.configure(bg="#1a1a2e")
        SPLASH_FONT = "Ubuntu" if any(f.lower().startswith("ubuntu") for f in font.families(_splash_root)) else "Sans"
        tk.Label(_splash_root, text="Моност", font=(SPLASH_FONT, 20, "bold"),
                 fg="white", bg="#1a1a2e").pack(pady=(35, 5))
        tk.Label(_splash_root, text="POS Систем", font=(SPLASH_FONT, 13),
                 fg="#aaaacc", bg="#1a1a2e").pack()
        tk.Label(_splash_root, text="Ачааллаж байна...", font=(SPLASH_FONT, 10),
                 fg="#8888aa", bg="#1a1a2e").pack(pady=(20, 0))
        _splash_root.update()
    except Exception as e:
        logger.debug(f"Splash unavailable: {e}")


def hide_splash():
    global _splash_root
    if _splash_root:
        try:
            _splash_root.destroy()
        except Exception:
            logger.warning("Unhandled exception in: except Exception:")
            pass
        _splash_root = None


def show_message(kind, title, message):
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if kind == "error":
            messagebox.showerror(title, message, parent=root)
        else:
            messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception:
        print(f"{kind.upper()}: {title}\n{message}")


class POSApplication:
    def __init__(self, start_minimized=False):
        self.start_minimized = start_minimized
        self.flask_thread = None
        self.cashier_window = None
        self.customer_window = None

    def start(self):
        logger.info("=== POS Ubuntu Desktop Starting ===")
        logger.info(f"Project: {ROOT_DIR}")
        logger.info(f"Python: {sys.version}")
        logger.info(f"Platform: {platform.platform()}")

        # DB integrity check
        try:
            import database as db
            db.init_db()
            from database import get_db
            with get_db() as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if result and result[0] != "ok":
                    logger.error(f"DB integrity check failed: {result[0]}")
                    show_message("error", "Өгөгдлийн сангийн алдаа",
                                 f"Өгөгдлийн сангийн бүрэн бүтэн байдал алдагдсан.\n\n{result[0]}\n\nТохиргоо хуудсаас нөөцөөс сэргээнэ үү.")
        except Exception as e:
            logger.warning(f"DB integrity check skipped: {e}")

        if not acquire_lock():
            logger.warning("Another instance is already running")
            show_message("error", "Программ ажиллаж байна",
                         "Программ аль хэдийн ажиллаж байна.\nTaskbar эсвэл tray хэсгийг шалгана уу.")
            sys.exit(0)

        flask_already_running = is_port_in_use(FLASK_PORT)
        if flask_already_running:
            logger.info(f"Flask already running on port {FLASK_PORT}, skipping server start")

        show_splash()

        if not flask_already_running:
            self.flask_thread = threading.Thread(target=run_flask, args=(FLASK_PORT,), daemon=True)
            self.flask_thread.start()
            logger.info(f"Flask server starting on port {FLASK_PORT}...")

            if not wait_for_server(FLASK_PORT):
                hide_splash()
                logger.error("Flask server failed to start within timeout")
                show_message("error", "Сервер асахгүй байна",
                             "Сервер ачааллахад алдаа гарлаа.\nlogs/pos.log файлыг шалгана уу.")
                release_lock()
                sys.exit(1)
            logger.info("Flask server is ready")

        # Auto-detect printer port on startup
        try:
            from printer import detect_printer_port
            port = detect_printer_port()
            logger.info(f"Printer port detected: {port}")
        except Exception as e:
            logger.warning(f"Printer detection failed: {e}")

        hide_splash()
        self._start_windows()
        release_lock()
        logger.info("Application exited")

    def _start_windows(self):
        import webview

        base_url = f"http://127.0.0.1:{FLASK_PORT}"

        self.cashier_window = webview.create_window(
            "Моност — Кассчин", f"{base_url}/",
            fullscreen=True, min_size=(1366, 768),
            text_select=False, confirm_close=False
        )
        logger.info("Cashier window created")

        secondary = get_secondary_monitor()
        if secondary:
            x, y, w, h = secondary
            self.customer_window = webview.create_window(
                "Моност — Үйлчлүүлэгч", "",
                x=x, y=y, width=w, height=h,
                fullscreen=True, text_select=False, confirm_close=False
            )
            logger.info(f"Customer window on secondary monitor ({x},{y})")
        else:
            self.customer_window = webview.create_window(
                "Моност — Үйлчлүүлэгч", "",
                fullscreen=True, text_select=False, confirm_close=False
            )
            logger.info("Customer window on primary monitor (no secondary found)")

        menu_items = [
            webview.menu.Menu("Цонх", [
                webview.menu.MenuAction("Үйлчлүүлэгч цонх харуулах", self._show_customer),
                webview.menu.MenuAction("Үйлчлүүлэгч цонх нуух", self._hide_customer),
                webview.menu.MenuSeparator(),
                webview.menu.MenuAction("Гарах", self._quit_app),
            ]),
            webview.menu.Menu("Тусламж", [
                webview.menu.MenuAction("Борлуулалт хийх заавар", self._show_help),
            ]),
        ]

        def _on_start():
            if self.customer_window:
                self.customer_window.load_url(f"{base_url}/customer")
            logger.info("Customer window navigated to /customer")

        logger.info("Starting webview event loop...")
        try:
            webview.start(func=_on_start, menu=menu_items, debug=False, http_server=False, private_mode=False)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Webview error: {e}")

    def _show_customer(self):
        if self.customer_window:
            self.customer_window.show()

    def _hide_customer(self):
        if self.customer_window:
            self.customer_window.hide()

    def _quit_app(self):
        import webview
        for w in webview.windows:
            w.destroy()

    def _show_help(self):
        show_message("info", "Борлуулалт хийх заавар",
                     "• Бар код сканнер ашиглана\n• Эсвэл барааны зураг дээр дарна\n"
                     "• F2 = Бэлнээр төлөх\n• F4 = Картаар төлөх\n• F5 = QR төлбөр\n"
                     "• F3 = Захиалга хүлээлгэх\n• ESC = Сагс цэвэрлэх\n"
                     "• Ctrl+F = Хайх\n• Сумнууд = Бараа сонгох\n• Enter = Сагсанд нэмэх")


def main():
    parser = argparse.ArgumentParser(description="POS Ubuntu Desktop")
    parser.add_argument("--tray", action="store_true")
    parser.add_argument("--dev", action="store_true", help="Enable development mode (auto-reload)")
    args = parser.parse_args()
    app = POSApplication(start_minimized=args.tray)
    app.start()


if __name__ == "__main__":
    main()
