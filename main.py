"""
Battery Lens — Main entry point.

Architecture:
- customtkinter requires ONE ctk.CTk() as the Tk root.
- The root is hidden (withdrawn) so the app lives purely in the system tray.
- AppWindow is a ctk.CTkToplevel child of that root — shown/hidden on demand.
- pystray runs in a daemon thread (it blocks its own thread).
- All GUI creation/modification must happen on the main thread via .after() or _tk_call_queue.
"""
import os
import sys
import threading
import time
import logging

# Configure logging FIRST, before any app imports.
# The directory must be computed using pure stdlib (no app imports yet).
import os as _os, sys as _sys

if _sys.platform == "win32":
    _log_dir = _os.path.join(
        _os.environ.get("APPDATA", _os.path.expanduser("~")), "BatteryLens"
    )
elif _sys.platform == "darwin":
    _log_dir = _os.path.join(
        _os.path.expanduser("~"), "Library", "Application Support", "BatteryLens"
    )
else:  # Linux / other — XDG_DATA_HOME, default ~/.local/share
    _xdg_data = _os.environ.get(
        "XDG_DATA_HOME",
        _os.path.join(_os.path.expanduser("~"), ".local", "share"),
    )
    _log_dir = _os.path.join(_xdg_data, "battery-lens")

_os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(
            _os.path.join(_log_dir, "battery_lens.log"), encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# ─────────────────────────────────────────────
# Application imports
# ─────────────────────────────────────────────
import customtkinter as ctk
from utils.platform_utils import get_app_data_dir, get_adapter
from core.database import Database
from services.monitor_service import MonitorService
from ui.tray import TrayIcon
from ui.app_window import AppWindow

# ─────────────────────────────────────────────
# SINGLE INSTANCE ENFORCEMENT — socket-based lock
# ─────────────────────────────────────────────
import socket
import atexit

_single_instance_socket: socket.socket = None
_LOCK_PORT = 47892


def check_single_instance() -> bool:
    """
    Binds a local TCP socket to a fixed port.
    Only one process can bind at a time — OS automatically releases on exit/crash.
    Returns True if we are the sole instance.
    """
    global _single_instance_socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        sock.bind(("127.0.0.1", _LOCK_PORT))
        sock.listen(1)
        _single_instance_socket = sock

        def _release():
            try:
                sock.close()
            except Exception:
                pass

        atexit.register(_release)
        return True
    except OSError:
        return False


# ─────────────────────────────────────────────
# FIRST-RUN DETECTION
# ─────────────────────────────────────────────

def _show_welcome(root: ctk.CTk):
    """Shows a simple welcome dialog on first launch."""
    win = ctk.CTkToplevel(root)
    win.title("Welcome to Battery Lens")
    win.geometry("480x360")
    win.resizable(False, False)
    win.grab_set()  # Modal

    ctk.CTkLabel(
        win,
        text="Welcome to Battery Lens",
        font=ctk.CTkFont(size=22, weight="bold"),
    ).pack(pady=(30, 10))

    msg = (
        "Battery Lens monitors your battery in the background.\n\n"
        "• It runs quietly in the system tray.\n"
        "• Click the tray icon to open the dashboard.\n"
        "• Anomaly alerts appear as notifications.\n\n"
        "All data is stored locally on your computer.\n"
        "Nothing is sent to the internet.\n\n"
        "The app needs a few charge/discharge cycles\n"
        "before it can detect anomalies."
    )
    ctk.CTkLabel(win, text=msg, justify="center", wraplength=420).pack(pady=10, padx=30)

    def _close():
        win.grab_release()
        win.destroy()

    ctk.CTkButton(win, text="Get Started", command=_close, width=160).pack(pady=20)
    root.wait_window(win)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    # 1. Single instance check
    if not check_single_instance():
        logger.warning("Battery Lens is already running.")
        _show_already_running_message()
        sys.exit(0)

    logger.info("Battery Lens starting up...")

    # 2. Initialize DB — use proper OS-specific path
    app_data = get_app_data_dir()
    db_path = str(app_data / "battery_lens.db")
    logger.info(f"Database path: {db_path}")

    try:
        db = Database(db_path)
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}", exc_info=True)
        _show_fatal_error("Database Error", f"Could not initialize the database:\n{e}")
        sys.exit(1)

    # 3. Detect platform and init adapter
    adapter = None
    try:
        adapter = get_adapter()
        if adapter is None:
            logger.warning(f"No battery adapter available for this platform ({sys.platform}). "
                           "Running in limited mode.")
    except Exception as e:
        logger.error(f"Failed to initialize platform adapter: {e}", exc_info=True)
        # Don't exit — run in limited mode (dashboard will show "No battery")

    # 4. Set up customtkinter appearance BEFORE creating any CTk windows
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    # 5. Create the ONE hidden Tk root (customtkinter's ctk.CTk IS the Tk root)
    _tk_root = ctk.CTk()
    _tk_root.withdraw()  # Keep hidden — app lives in tray

    # 6. Start Monitor Service (only if adapter available)
    monitor = None
    if adapter is not None:
        monitor = MonitorService(db, adapter)
    else:
        # Minimal no-op monitor so the rest of the app can run
        logger.info("Running in no-battery / limited mode — monitoring disabled.")

    # 7. App state
    app_window: AppWindow = None
    tray_icon: TrayIcon = None
    _shutdown_event = threading.Event()
    _tk_call_queue = []

    def on_show_dashboard(tab_name: str = "Dashboard"):
        nonlocal app_window
        def _show():
            nonlocal app_window
            if app_window is None:
                app_window = AppWindow(_tk_root, db, on_window_close, monitor)
            app_window.show_window(tab_name)

        if app_window is not None and app_window.winfo_exists():
            app_window.after(0, _show)
        else:
            _tk_call_queue.append(_show)

    def on_window_close():
        pass  # Window is hidden (withdrawn), tray icon stays

    def on_exit():
        logger.info("User requested exit.")
        _shutdown_event.set()

    # 8. Create tray icon
    tray_icon = TrayIcon(db, on_show_dashboard, on_exit)

    # 9. Wire anomaly notifications → tray
    def on_anomaly(title: str, message: str):
        tray_icon.show_notification(title, message)

    if monitor is not None:
        monitor.on_anomaly_detected = on_anomaly
        monitor.start()

    # 10. Start tray icon in background thread
    tray_thread = threading.Thread(target=tray_icon.run, name="TrayThread", daemon=True)
    tray_thread.start()

    # 11. Tray updater thread — updates icon with latest snapshot
    def tray_updater():
        while not _shutdown_event.is_set():
            try:
                snapshots = db.get_recent_battery_snapshots(limit=1)
                if snapshots:
                    tray_icon.update(snapshots[0])
            except Exception as e:
                logger.debug(f"Tray update error: {e}")
            poll_interval = monitor.poll_interval if monitor else 30
            time.sleep(poll_interval)

    updater_thread = threading.Thread(target=tray_updater, name="TrayUpdater", daemon=True)
    updater_thread.start()

    # 12. Process tk call queue on main thread
    def _process_queue():
        while _tk_call_queue:
            try:
                fn = _tk_call_queue.pop(0)
                fn()
            except Exception as e:
                logger.error(f"Error in tk call queue: {e}", exc_info=True)

        if _shutdown_event.is_set():
            _do_shutdown()
        else:
            _tk_root.after(200, _process_queue)

    def _do_shutdown():
        logger.info("Shutting down...")
        if monitor:
            monitor.stop()
        if tray_icon:
            tray_icon.stop()
        try:
            if app_window and app_window.winfo_exists():
                app_window.destroy()
            _tk_root.destroy()
        except Exception:
            pass

    _tk_root.after(200, _process_queue)

    # 13. First-run welcome dialog (shown on the Tk root's event loop)
    is_first_run = db.get_setting("first_run_done") != "1"
    if is_first_run:
        _tk_root.after(500, lambda: (_show_welcome(_tk_root), db.update_setting("first_run_done", "1")))

    # 14. Run Tkinter main loop (blocks until _tk_root.destroy() is called)
    try:
        _tk_root.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        if monitor:
            monitor.stop()
        logger.info("Battery Lens shut down cleanly.")


def _show_already_running_message():
    try:
        root = ctk.CTk()
        root.withdraw()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        win = ctk.CTkToplevel(root)
        win.title("Battery Lens")
        win.geometry("360x160")
        win.resizable(False, False)
        ctk.CTkLabel(win, text="Battery Lens is already running.\nLook for its icon in the system tray.",
                     justify="center").pack(pady=30)
        ctk.CTkButton(win, text="OK", command=root.destroy).pack()
        root.mainloop()
    except Exception:
        print("Battery Lens is already running.", file=sys.stderr)


def _show_fatal_error(title: str, message: str):
    try:
        root = ctk.CTk()
        root.withdraw()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        win = ctk.CTkToplevel(root)
        win.title(title)
        win.geometry("400x200")
        win.resizable(False, False)
        ctk.CTkLabel(win, text=f"{title}\n\n{message}", justify="center", wraplength=360).pack(pady=30)
        ctk.CTkButton(win, text="OK", command=root.destroy).pack()
        root.mainloop()
    except Exception:
        print(f"FATAL ERROR — {title}: {message}", file=sys.stderr)


if __name__ == "__main__":
    main()
