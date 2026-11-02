"""BillFlow launcher: choose the database, start the server, open the interface."""
import argparse
import os
import sys
import threading
import time
import urllib.request
import webbrowser

from billflow import database, dbsetup, onboarding
from billflow.dbconfig import DatabaseConfigError
from billflow.sample_data import is_empty, load_sample_data
from billflow.web.server import create_server, startup_message

DEFAULT_PORT = 5050


def wait_for_server(port, timeout=5.0):
    start = time.time()
    url = f"http://127.0.0.1:{port}/api/setup/state"
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
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as e:
        print(f"[!] PySide6 WebEngine not available: {e}. Falling back to browser...")
        launch_browser(port)
        return

    app = QApplication(sys.argv)
    app.setApplicationName("BillFlow")

    window = QMainWindow()
    window.setWindowTitle("BillFlow")
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


def build_parser():
    parser = argparse.ArgumentParser(description="BillFlow: sales, billing and inventory")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to run the server on (default: {DEFAULT_PORT})")
    parser.add_argument("--desktop", action="store_true", help="Open in a native desktop window")
    parser.add_argument("--web", action="store_true", help="Open in the web browser")

    shared = parser.add_argument_group("sharing with phones and other devices")
    shared.add_argument("--lan", action="store_true",
                        help="Let phones and other devices on your network use BillFlow (they sign in with an access PIN)")
    shared.add_argument("--host", help="Address to listen on (default: 127.0.0.1, or 0.0.0.0 with --lan)")
    shared.add_argument("--pin", help="Set the access PIN used in --lan mode (4 to 12 digits)")

    data = parser.add_argument_group("database")
    data.add_argument("--list-databases", action="store_true", help="Show the database types BillFlow supports, then exit")
    data.add_argument("--setup-db", action="store_true", help="Choose and save the database (guided)")
    data.add_argument("--db", metavar="URL",
                      help="Use this database for this run, e.g. postgresql://user:password@localhost/billflow "
                           "(also: the BILLFLOW_DB environment variable)")
    data.add_argument("--sample-data", action="store_true", help="Fill an empty database with sample data to try BillFlow")
    return parser


def yes(answer: str, default: bool) -> bool:
    answer = answer.strip().lower()
    return default if not answer else answer in ("y", "yes")


def needs_setup(args) -> bool:
    """A first run: nothing has chosen a database yet, so the setup screen comes first."""
    return not (args.db or args.sample_data or args.setup_db or onboarding.is_complete())


def listen_host(args) -> str:
    """This computer only, or the whole network when --lan or the setup screen asked for phones to be let in."""
    return args.host or ("0.0.0.0" if args.lan or onboarding.share_on_network() else "127.0.0.1")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_databases:
        print(dbsetup.describe_engines())
        try:
            print(f"\nIn use now: {database.configure(args.db).display}")
        except DatabaseConfigError as exc:
            print(f"\n{exc}")
        return 0

    host = listen_host(args)
    if args.pin and host in ("127.0.0.1", "localhost", "::1"):
        parser.error("--pin only applies when BillFlow is shared on the network (use --lan)")

    if args.setup_db:
        chosen = dbsetup.run_wizard()
        if chosen is None:
            return 1
        args.db = chosen.url

    first_run = needs_setup(args)
    if first_run:
        print("First run: the setup screen will open so you can choose the database, time zone and shop details.", flush=True)
    else:
        try:
            target = database.configure(args.db)
        except DatabaseConfigError as exc:
            return f"{exc}\nChoose a database with:  python run.py --setup-db"
        try:
            database.init_db()
        except DatabaseConfigError as exc:  # e.g. the driver for this database type is not installed
            return f"{exc}\nOr choose another database with:  python run.py --setup-db"
        except Exception as exc:
            return (f"Cannot open the database ({target.display}):\n  {type(exc).__name__}: {exc}\n"
                    "Check it is running, or choose another with:  python run.py --setup-db")

        if args.sample_data:
            load_sample_data()
        elif args.setup_db and is_empty() and yes(input("Fill it with sample data so you can try BillFlow? [y/N]: "), False):
            load_sample_data()
        if args.setup_db and not yes(input("Start BillFlow now? [Y/n]: "), True):
            return 0
        print(f"Database: {target.display}", flush=True)

    # Bind here, not in the thread, so a busy port or a bad --pin stops us with a clear message
    try:
        server = create_server(host, args.port, args.pin, setup_pending=first_run)
    except OSError as exc:
        return f"Cannot listen on {host}:{args.port}: {exc}"
    except ValueError as exc:
        return str(exc)
    print(startup_message(server), flush=True)

    # Serve the API & web UI from a background daemon thread
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not wait_for_server(args.port):
        print(f"[!] Warning: Server did not respond within timeout on port {args.port}")

    if args.web:
        launch_browser(args.port)
    elif args.desktop:
        launch_desktop(args.port)
    elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        launch_desktop(args.port)
    else:
        launch_browser(args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
