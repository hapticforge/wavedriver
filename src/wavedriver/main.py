"""
Wavedriver Web UI Launcher and PyWebView Bridge.

This module provides the main entry point to start the motor controller and
launches the PyWebView desktop app GUI, exposing a Python-to-JS bridge API.
It performs parameter validations and legacy migrations.
"""

import argparse
import datetime
import importlib.metadata
import json
import logging
import mimetypes
import os
import platform
import signal
import socket as _socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

# Must be set before webview initializes its Qt/GTK backend to suppress the GTK probe error.
os.environ.setdefault("PYWEBVIEW_GUI", "qt")


import webview  # noqa: E402

from wavedriver.motor_controller import MotorController
from wavedriver.patterns import PATTERN_REGISTRY
from wavedriver.storage import SessionData, Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wavedriver")


# ── API result types ──────────────────────────────────────────────────────────


class _CommandResultRequired(TypedDict):
    success: bool


class CommandResult(_CommandResultRequired, total=False):
    """Return type for every command call.

    ``success`` is always present.  On failure, ``error`` carries the human-readable
    message and ``error_kind`` classifies the failure:

    - ``"user"``: invalid input the caller can fix (unknown pattern, out-of-range value).
    - ``"system"``: unexpected I/O or internal fault; details are also logged server-side.
    """

    error: str
    error_kind: Literal["user", "system"]


def _rebuild_frontend_if_stale() -> None:
    """Rebuild the Vite bundle when any web/src file is newer than the current dist output.

    Runs npm run build in the web/ directory.  Skips silently if npm is not
    found (production installs that ship a pre-built bundle).
    """
    web_dir = Path(__file__).resolve().parent / "web"
    dist_dir = web_dir / "dist" / "assets"

    # Find the newest source file under web/src/
    src_files = list((web_dir / "src").rglob("*"))
    if not src_files:
        return
    newest_src = max(f.stat().st_mtime for f in src_files if f.is_file())

    # Find the newest file in dist/assets/ (the compiled output)
    dist_files = list(dist_dir.glob("*")) if dist_dir.exists() else []
    newest_dist = max((f.stat().st_mtime for f in dist_files if f.is_file()), default=0.0)

    if newest_src <= newest_dist:
        return

    logger.info("Frontend sources changed — rebuilding bundle (npm run build)…")
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=web_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Frontend build succeeded.")
        else:
            logger.error("Frontend build failed:\n%s", result.stderr or result.stdout)
            sys.exit(1)
    except FileNotFoundError:
        logger.warning("npm not found — skipping frontend rebuild (using existing dist/).")


def _install_signal_handlers(controller: "MotorController") -> None:
    """Install SIGTERM/SIGINT handlers that stop the controller before exit.

    The ``finally`` block in ``main()`` handles normal window close and
    KeyboardInterrupt, but SIGTERM (e.g. ``kill PID``) terminates the process
    immediately without running Python cleanup.  These handlers ensure the motor
    is placed in SleepMode regardless of how the process exits.
    """

    def _handle(signum: int, frame: object) -> None:
        logger.info("Signal %d received — stopping controller and exiting", signum)
        controller.stop()
        os._exit(0)

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


class _MpvController:
    """Drives an mpv subprocess via its JSON IPC socket for video sync."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._sock: _socket.socket | None = None
        self._sock_path: str = ""
        self._lock = threading.Lock()
        self._buf = b""

    def launch(self, video_path: str) -> bool:
        """Start mpv with *video_path*.  Returns False if mpv is not installed."""
        self.close()
        self._sock_path = os.path.join(tempfile.gettempdir(), "wavedriver-mpv.sock")
        try:
            if os.path.exists(self._sock_path):
                os.unlink(self._sock_path)
            self._proc = subprocess.Popen(
                ["mpv", f"--input-ipc-server={self._sock_path}", "--pause", video_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return False

        for _ in range(30):  # wait up to 3 s for socket to appear
            if os.path.exists(self._sock_path):
                break
            time.sleep(0.1)
        else:
            return False

        self._connect()
        return True

    def _connect(self) -> None:
        try:
            sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            sock.connect(self._sock_path)
            sock.settimeout(0.5)
            self._sock = sock
            self._buf = b""
        except Exception:
            self._sock = None

    def _send(self, cmd: list[Any]) -> dict[str, Any] | None:
        with self._lock:
            if not self._sock:
                return None
            try:
                self._sock.sendall((json.dumps({"command": cmd}) + "\n").encode())
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline:
                    try:
                        chunk = self._sock.recv(4096)
                        if not chunk:
                            break
                        self._buf += chunk
                    except _socket.timeout:
                        pass
                    while b"\n" in self._buf:
                        line, self._buf = self._buf.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj: dict[str, Any] = json.loads(line)
                            if "error" in obj:
                                return obj
                        except Exception:
                            pass
            except Exception:
                self._sock = None
        return None

    def get_position(self) -> float | None:
        r = self._send(["get_property", "time-pos"])
        if r and r.get("error") == "success" and r.get("data") is not None:
            return float(r["data"])
        return None

    def is_paused(self) -> bool:
        r = self._send(["get_property", "pause"])
        if r and r.get("error") == "success":
            return bool(r["data"])
        return True

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def close(self) -> None:
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        if self._sock_path and os.path.exists(self._sock_path):
            try:
                os.unlink(self._sock_path)
            except Exception:
                pass


class _AppHTTPHandler(BaseHTTPRequestHandler):
    """Serves the frontend bundle (static files) and a single video file over HTTP.

    Routing:
      GET /video  — streams the currently loaded video with Range support.
      GET *       — serves files from dist_dir; falls back to index.html for SPA routes.
    """

    def do_HEAD(self) -> None:
        self._dispatch(head_only=True)

    def do_GET(self) -> None:
        self._dispatch(head_only=False)

    def _dispatch(self, head_only: bool) -> None:
        srv = cast("_AppHTTPServer", self.server)
        clean = self.path.split("?")[0].rstrip("/") or "/"

        if clean == "/video":
            self._serve_video(srv.video_path, head_only)
        else:
            self._serve_static(srv.dist_dir, clean, head_only)

    def _serve_static(self, dist_dir: Path | None, clean_path: str, head_only: bool) -> None:
        if dist_dir is None:
            self.send_error(404)
            return
        candidate = dist_dir / clean_path.lstrip("/") if clean_path != "/" else dist_dir / "index.html"
        if not candidate.is_file():
            candidate = dist_dir / "index.html"
        if not candidate.is_file():
            self.send_error(404)
            return
        data = candidate.read_bytes()
        ct = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _serve_video(self, video_path: str, head_only: bool) -> None:
        if not video_path or not os.path.isfile(video_path):
            self.send_error(404)
            return
        file_size = os.path.getsize(video_path)
        ct = mimetypes.guess_type(video_path)[0] or "application/octet-stream"
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            rng = range_header[6:].split("-")
            start = int(rng[0]) if rng[0] else 0
            end = int(rng[1]) if len(rng) > 1 and rng[1] else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            if not head_only:
                with open(video_path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
        else:
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            if not head_only:
                with open(video_path, "rb") as f:
                    self.wfile.write(f.read())

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _AppHTTPServer(socketserver.TCPServer):
    """Background HTTP server that serves the frontend bundle and streams video files."""

    allow_reuse_address = True

    def __init__(self, dist_dir: Path | None = None) -> None:
        self.dist_dir: Path | None = dist_dir
        self.video_path: str = ""
        super().__init__(("127.0.0.1", 0), _AppHTTPHandler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return cast(tuple[str, int], self.server_address)[1]


class WebviewAPI:
    """API bridge exposed to the JavaScript frontend inside PyWebView."""

    def __init__(
        self,
        controller: MotorController,
        initial_safety_limit_N: float,
        storage: Storage | None = None,
        app_server: "_AppHTTPServer | None" = None,
    ) -> None:
        self.controller = controller
        self.safety_limit_N = initial_safety_limit_N
        self.storage = storage if storage is not None else Storage()
        self.window: Any = None
        self._app_server = app_server
        self._mpv = _MpvController()

    def set_window(self, window: Any) -> None:
        """Sets the pywebview window instance reference."""
        self.window = window

    def quit_application(self) -> CommandResult:
        """Closes the desktop UI window and exits the application."""
        if self.window:
            self.window.destroy()
            return {"success": True}
        return {"success": False, "error": "Window handle not set", "error_kind": "system"}

    def get_telemetry(self) -> dict[str, Any]:
        """Fetches thread-safe controller telemetry and sanitizes non-serializable fields."""
        try:
            tel = self.controller.get_telemetry()
            if "state_enum" in tel:
                tel["state_enum"] = tel["state_enum"].name
            return tel
        except Exception as e:
            return {"error": str(e)}

    def send_command(self, cmd_type: str, kwargs: dict[str, Any] | None = None) -> CommandResult:
        """Processes and forwards commands from the frontend to the controller."""
        if kwargs is None:
            kwargs = {}

        try:
            if cmd_type == "start_pattern":
                pattern_name = kwargs.pop("pattern_name", "Wave")
                params: dict[str, Any] = kwargs.get("params", {})

                entry = PATTERN_REGISTRY.get(pattern_name)
                if entry is None:
                    return {
                        "success": False,
                        "error": f"Unknown pattern name: {pattern_name}",
                        "error_kind": "user",
                    }

                stroke_um = float(params.get("stroke_length_um", 50000.0))
                freq_hz = float(params.get("frequency_hz", 1.0))
                params["_max_catch_up_speed_um_s"] = entry.peak_speed_um_s(stroke_um, freq_hz)
                params["_pattern_name"] = pattern_name
                self.controller.send_command(
                    "start_pattern", pattern_func=entry.func, params=params
                )
                return {"success": True}

            self.controller.send_command(cmd_type, **kwargs)
            return {"success": True}
        except Exception as e:
            logger.error("send_command(%r) raised: %s", cmd_type, e)
            return {"success": False, "error": str(e), "error_kind": "system"}

    def load_presets(self) -> dict[str, Any]:
        """Loads saved configurations from presets file.

        Returns the presets dict directly (not wrapped in a success envelope).
        Returns ``{}`` on any error — the Storage layer already handles and logs corruption.
        """
        try:
            return self.storage.load_presets()
        except Exception as e:
            logger.error("Failed to load presets: %s", e)
            return {}

    def save_presets(self, presets_data: dict[str, Any]) -> CommandResult:
        """Saves current presets to preset slots file."""
        try:
            self.storage.save_presets(presets_data)
            return {"success": True}
        except Exception as e:
            logger.error("Failed to save presets: %s", e)
            return {"success": False, "error": str(e), "error_kind": "system"}

    def load_session(self) -> SessionData:
        """Loads safety settings from the local session file.

        Only safety-relevant settings (force limit, session timer) are persisted and
        restored across runs.  Motion parameters (pattern, frequency, stroke, etc.) are
        always reset to defaults so calibration is required each session.
        """
        try:
            return self.storage.load_session(self.safety_limit_N)
        except Exception as e:
            logger.error("Failed to load session: %s", e)
            return SessionData(
                safety_force_n=self.safety_limit_N, max_session_s=0, history_enabled=True
            )

    def save_session(self, session_data: dict[str, Any]) -> CommandResult:
        """Saves safety settings to the local session file."""
        try:
            self.storage.save_session(session_data, self.safety_limit_N)
            return {"success": True}
        except Exception as e:
            logger.error("Failed to save session: %s", e)
            return {"success": False, "error": str(e), "error_kind": "system"}

    def save_session_history(self, record: dict[str, Any]) -> CommandResult:
        """Appends a completed session record to the JSONL history log."""
        try:
            self.storage.append_history(record)
            return {"success": True}
        except Exception as e:
            logger.error("Failed to write session history: %s", e)
            return {"success": False, "error": str(e), "error_kind": "system"}

    def load_session_history(self) -> list[dict[str, Any]]:
        """Returns the most recent 20 session history records, newest first."""
        try:
            return self.storage.load_history()
        except Exception as e:
            logger.warning("Failed to load session history: %s", e)
            return []

    def get_diagnostics(self) -> dict[str, Any]:
        """Returns a scrubbed diagnostics snapshot for support purposes.

        Includes device state, recent events, and system info.
        Does NOT include session history, pattern parameters, or personal data.
        """
        try:
            version = importlib.metadata.version("wavedriver")
        except importlib.metadata.PackageNotFoundError:
            version = "dev"

        tel = self.controller.get_telemetry()
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "app_version": version,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "use_mock": tel.get("use_mock", False),
            "state": tel.get("state", "unknown"),
            "error_msg": tel.get("error_msg", ""),
            "temperature_C": tel.get("temperature_C", 0),
            "voltage_mV": tel.get("voltage_mV", 0),
            "errors_bitmask": tel.get("errors_bitmask", 0),
            "safety_limit_N": self.safety_limit_N,
            "event_log": tel.get("event_log", []),
        }

    def clear_history(self) -> CommandResult:
        """Deletes all session history records from disk."""
        try:
            self.storage.clear_history()
            return {"success": True}
        except Exception as e:
            logger.error("Failed to clear history: %s", e)
            return {"success": False, "error": str(e), "error_kind": "system"}

    def pick_and_launch_video(self) -> dict[str, Any]:
        """Open a native file dialog, then launch the chosen video in mpv.

        mpv is controlled via its JSON IPC socket.  Returns the filename so the
        frontend can display it.  Returns an error dict if mpv is not installed.
        """
        if not self.window:
            return {"success": False, "error": "Window not ready", "error_kind": "system"}

        result = self.window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("Video Files (*.mp4;*.m4v;*.webm;*.mkv;*.mov;*.avi;*.mpeg;*.mpg)",),
        )
        if not result:
            return {"success": False, "error": "No file selected", "error_kind": "user"}

        path = str(result[0])
        if not self._mpv.launch(path):
            return {
                "success": False,
                "error": "mpv not found — install mpv to use video sync",
                "error_kind": "system",
            }

        return {"success": True, "filename": os.path.basename(path)}

    def get_video_position(self) -> dict[str, Any]:
        """Return current playback position and paused state from mpv."""
        if not self._mpv.alive():
            return {"success": False, "error": "No video playing"}
        pos = self._mpv.get_position()
        paused = self._mpv.is_paused()
        return {"success": True, "position_s": pos, "paused": paused}

    def close_video(self) -> CommandResult:
        """Stop and close the mpv subprocess."""
        self._mpv.close()
        return {"success": True}

    def connect_port(self, port: str) -> CommandResult:
        """Stops the active connection thread and restarts it on the chosen port."""
        try:
            logger.info("Reconnecting motor controller to port: %s", port)
            self.controller.stop()
            self.controller.start(port=port, baud=self.controller.baud)
            return {"success": True}
        except Exception as e:
            logger.error("Failed to connect to port %s: %s", port, e)
            return {"success": False, "error": str(e), "error_kind": "system"}

    def list_ports(self) -> list[dict[str, str]]:
        """Enumerates and returns available system serial ports."""
        try:
            import serial.tools.list_ports

            ports = sorted(serial.tools.list_ports.comports())
            # Filter out motherboard / generic TTY ports with 'n/a' description or motherboard ttyS devices
            filtered = [
                {"device": p.device, "description": p.description}
                for p in ports
                if p.description
                and p.description.lower() != "n/a"
                and not p.device.startswith("/dev/ttyS")
            ]
            return filtered
        except Exception as e:
            logger.warning("Failed to list serial ports: %s", e)
            return []


def main() -> None:
    """Parses command-line arguments and launches the Wavedriver PyWebView app."""
    parser = argparse.ArgumentParser(
        description="Wavedriver: Graphical Dashboard for Iris Dynamics Orca 6 Linear Motor"
    )
    parser.add_argument(
        "--port",
        type=str,
        default="/dev/ttyUSB0",
        help="Serial port path (e.g. /dev/ttyUSB0, COM3). Default: /dev/ttyUSB0",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=19200,
        help="Baud rate for Modbus communication. Default: 19200",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in simulation/mock mode (no physical hardware required)",
    )
    parser.add_argument(
        "--safety-limit",
        type=float,
        default=55.0,
        help="Software safety feedback force threshold in Newtons (N). Default: 55.0 N",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in frontend development mode (connects to Vite dev server)",
    )
    parser.add_argument(
        "--list-ports", action="store_true", help="List available serial ports and exit"
    )

    args = parser.parse_args()

    if args.list_ports:
        try:
            import serial.tools.list_ports

            ports = sorted(serial.tools.list_ports.comports())
            if ports:
                print("Available serial ports:")
                for p in ports:
                    print(f"  {p.device:<20}  {p.description}")
            else:
                print("No serial ports found.")
        except ImportError:
            print("pyserial not installed; cannot enumerate ports.")
        sys.exit(0)

    if not (1.0 <= args.safety_limit <= 60.0):
        parser.error(f"--safety-limit must be between 1.0 and 60.0 N (got {args.safety_limit})")

    logger.info("Initializing Wavedriver Web Dashboard (Mock Mode: %s)", args.mock)

    controller = MotorController(use_mock=args.mock)

    safety_mN = int(args.safety_limit * 1000.0)
    controller.send_command("set_safety_limit", limit_mN=safety_mN)

    controller.start(port=args.port, baud=args.baud)
    _install_signal_handlers(controller)

    dist_dir = Path(__file__).resolve().parent / "web" / "dist"

    if args.dev:
        # Vite dev server handles the frontend; start a bare server just for video.
        app_server = _AppHTTPServer(dist_dir=None)
        url = "http://localhost:5173?platform=pywebview"
    else:
        _rebuild_frontend_if_stale()
        if not (dist_dir / "index.html").exists():
            logger.error("Compiled frontend not found at %s. Run 'npm run build' first.", dist_dir)
            controller.stop()
            sys.exit(1)
        app_server = _AppHTTPServer(dist_dir=dist_dir)
        url = f"http://127.0.0.1:{app_server.port}/?platform=pywebview"
        logger.info("Serving frontend from http://127.0.0.1:%d/", app_server.port)

    api = WebviewAPI(
        controller=controller,
        initial_safety_limit_N=args.safety_limit,
        app_server=app_server,
    )

    logger.info("Opening desktop UI window targeting: %s", url)

    window = webview.create_window(
        title="Wavedriver Orca 6 Dashboard",
        url=url,
        js_api=api,
        width=1000,
        height=720,
        min_size=(900, 650),
        background_color="#0d0e15",
    )
    api.set_window(window)

    try:
        webview.start()
    finally:
        logger.info("Shutting down motor controller...")
        api._mpv.close()
        controller.stop()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
