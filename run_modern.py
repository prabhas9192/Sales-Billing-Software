#!/usr/bin/env python3
"""
BillFlow Next-Gen UI Launcher
Supports both Native Desktop (PySide6 QtWebEngine) and Web Browser modes.
"""
import argparse
import os
import sys
import threading
import time
import urllib.request
import webbrowser

# Ensure billflow package is importable
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from billflow.database import init_db
from billflow.web.server import run_server

DEFAULT_PORT = 5050


def wait_for_server(port, timeout=5.0):
    start = time.time()
    url = f"http://127.0.0.1:{port}/api/overview"
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def launch_desktop(port):
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as e:
        print(f"[!] PySide6 WebEngine not available: {e}. Falling back to browser...")
        launch_browser(port)
        return

    app = QApplication(sys.argv)
    app.setApplicationName("BillFlow Next-Gen")

    window = QMainWindow()
    window.setWindowTitle("BillFlow Next-Gen Sales & POS Suite (shadcn/ui)")
    window.resize(1300, 850)

    web_view = QWebEngineView()
    web_view.setUrl(QUrl(f"http://127.0.0.1:{port}/"))

    window.setCentralWidget(web_view)
    window.show()

    print(f"Native Desktop window open. Rendering on port {port}.")
    sys.exit(app.exec())


def launch_browser(port):
    url = f"http://127.0.0.1:{port}/"
    print(f"Opening BillFlow in default browser: {url}")
    webbrowser.open(url)
    print("Press Ctrl+C to stop server...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")


def main():
    parser = argparse.ArgumentParser(description="BillFlow Next-Gen Modern UI Launcher")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to run the server on (default: 5050)")
    parser.add_argument("--desktop", action="store_true", help="Launch in native desktop Qt window")
    parser.add_argument("--web", action="store_true", help="Launch in web browser")
    args = parser.parse_args()

    # Ensure database tables exist
    init_db()

    # Start API & web server in background daemon thread
    server_thread = threading.Thread(target=run_server, kwargs={"port": args.port}, daemon=True)
    server_thread.start()

    if not wait_for_server(args.port):
        print(f"[!] Warning: Server did not respond within timeout on port {args.port}")

    if args.web:
        launch_browser(args.port)
    elif args.desktop:
        launch_desktop(args.port)
    else:
        # Default: Try desktop window if DISPLAY is set, else browser
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            launch_desktop(args.port)
        else:
            launch_browser(args.port)


if __name__ == "__main__":
    main()
