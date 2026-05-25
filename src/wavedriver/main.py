"""
Wavedriver Web UI Launcher and PyWebView Bridge.

This module provides the main entry point to start the motor controller and
launches the PyWebView desktop app GUI, exposing a Python-to-JS bridge API.
It performs parameter validations and legacy migrations.
"""

import argparse
import subprocess
import sys
import json
import math
import logging
import datetime
import os
import webview

# Tell pywebview to use Qt directly rather than probing GTK first.
# Without this it logs a noisy (but harmless) GTK/gi import error on every launch.
os.environ.setdefault("PYWEBVIEW_GUI", "qt")
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wavedriver")

from wavedriver.motor_controller import MotorController, ControllerState
from wavedriver import patterns


def _rebuild_frontend_if_stale() -> None:
    """Rebuild the Vite bundle when any web/src file is newer than the current dist output.

    Runs npm run build in the web/ directory.  Skips silently if npm is not
    found (production installs that ship a pre-built bundle).
    """
    web_dir  = Path(__file__).resolve().parent / "web"
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

SESSION_FILE = Path.home() / ".config" / "wavedriver" / "session.json"
PRESETS_FILE = Path.home() / ".config" / "wavedriver" / "presets.json"
HISTORY_FILE = Path.home() / ".config" / "wavedriver" / "history.jsonl"

_VALID_PATTERNS = {"Wave", "Realistic", "Thrust", "Pulse", "Tease", "Escalate", "Edge", "Depth"}


def _pattern_peak_speed_um_s(pattern_name: str, stroke_length_um: float, frequency_hz: float) -> float:
    """Return the approximate peak velocity (µm/s) for a given pattern at its configured settings.

    Used to cap catch-up speed so the motor never repositions faster than it would move
    during normal pattern execution.
    """
    f = max(frequency_hz, 0.01)
    A = stroke_length_um / 2.0
    if pattern_name == "Pulse":
        # 4 sine cycles compressed into 70% of the period
        return (4.0 / 0.70) * math.pi * f * A
    elif pattern_name == "Thrust":
        # fast stroke traverses 2A in 20% of the period
        return 2.0 * A * f / 0.20
    elif pattern_name == "Realistic":
        # slider-crank is asymmetric; ~50% faster peak than sine at same params
        return 1.5 * math.pi * f * A
    else:
        # Wave, Tease, Escalate, Edge, Depth: sine-wave formula
        # (Depth modulates amplitude downward; peak is at full stroke)
        return math.pi * f * A


class WebviewAPI:
    """API bridge exposed to the JavaScript frontend inside PyWebView."""

    def __init__(self, controller: MotorController, initial_safety_limit_N: float):
        self.controller = controller
        self.safety_limit_N = initial_safety_limit_N
        self.window = None

    def set_window(self, window):
        """Sets the pywebview window instance reference."""
        self.window = window

    def quit_application(self) -> dict:
        """Closes the desktop UI window and exits the application."""
        if self.window:
            self.window.destroy()
            return {"success": True}
        return {"success": False, "error": "Window handle not set"}

    def get_telemetry(self) -> dict:
        """Fetches thread-safe controller telemetry and sanitizes non-serializable fields."""
        try:
            tel = self.controller.get_telemetry()
            if "state_enum" in tel:
                tel["state_enum"] = tel["state_enum"].name
            return tel
        except Exception as e:
            return {"error": str(e)}

    def send_command(self, cmd_type: str, kwargs: dict = None) -> dict:
        """Processes and forwards commands from the frontend to the controller."""
        if kwargs is None:
            kwargs = {}

        try:
            if cmd_type == "start_pattern":
                pattern_name = kwargs.pop("pattern_name", "Wave")
                params = kwargs.get("params", {})

                if pattern_name == "Wave":
                    pattern_func = patterns.wave_pattern
                elif pattern_name == "Realistic":
                    pattern_func = patterns.realistic_pattern
                elif pattern_name == "Thrust":
                    pattern_func = patterns.thrust_pattern
                elif pattern_name == "Pulse":
                    pattern_func = patterns.pulse_pattern
                elif pattern_name == "Tease":
                    pattern_func = patterns.tease_pattern
                elif pattern_name == "Escalate":
                    pattern_func = patterns.escalate_pattern
                elif pattern_name == "Edge":
                    pattern_func = patterns.edge_pattern
                elif pattern_name == "Depth":
                    pattern_func = patterns.depth_pattern
                else:
                    return {"success": False, "error": f"Unknown pattern name: {pattern_name}"}

                stroke_um = float(params.get("stroke_length_um", 50000.0))
                freq_hz   = float(params.get("frequency_hz", 1.0))
                params["_max_catch_up_speed_um_s"] = _pattern_peak_speed_um_s(
                    pattern_name, stroke_um, freq_hz
                )
                params["_pattern_name"] = pattern_name
                self.controller.send_command("start_pattern", pattern_func=pattern_func, params=params)
                return {"success": True}

            self.controller.send_command(cmd_type, **kwargs)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_presets(self) -> dict:
        """Loads saved configurations from presets file."""
        try:
            if PRESETS_FILE.exists():
                return json.loads(PRESETS_FILE.read_text())
        except Exception:
            pass
        return {}

    def save_presets(self, presets_data: dict) -> dict:
        """Saves current presets to preset slots file."""
        try:
            PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
            PRESETS_FILE.write_text(json.dumps(presets_data))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_session(self) -> dict:
        """Loads safety settings from the local session file.

        Only safety-relevant settings (force limit, session timer) are persisted and
        restored across runs.  Motion parameters (pattern, frequency, stroke, etc.) are
        always reset to defaults so calibration is required each session.
        """
        defaults = {"safety_force_n": self.safety_limit_N, "max_session_s": 0}
        try:
            if SESSION_FILE.exists():
                data = json.loads(SESSION_FILE.read_text())
                return {
                    "safety_force_n": max(1.0, min(60.0, float(data.get("safety_force_n", self.safety_limit_N)))),
                    "max_session_s":  max(0, min(7200,   int(data.get("max_session_s", 0)))),
                }
        except Exception:
            pass
        return defaults

    def save_session(self, session_data: dict) -> dict:
        """Saves safety settings to the local session file."""
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            to_save = {
                "safety_force_n": session_data.get("safety_force_n", self.safety_limit_N),
                "max_session_s":  session_data.get("max_session_s", 0),
            }
            SESSION_FILE.write_text(json.dumps(to_save))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_session_history(self, record: dict) -> dict:
        """Appends a completed session record to the JSONL history log."""
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            record["timestamp"] = datetime.datetime.now().isoformat()
            with open(HISTORY_FILE, "a") as f:
                f.write(json.dumps(record) + "\n")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_session_history(self) -> list:
        """Returns the most recent 20 session history records, newest first."""
        try:
            if HISTORY_FILE.exists():
                lines = [l for l in HISTORY_FILE.read_text().strip().splitlines() if l]
                records = []
                for line in lines[-20:]:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
                return list(reversed(records))
        except Exception:
            pass
        return []


def main():
    """Parses command-line arguments and launches the Wavedriver PyWebView app."""
    parser = argparse.ArgumentParser(
        description="Wavedriver: Graphical Dashboard for Iris Dynamics Orca 6 Linear Motor"
    )
    parser.add_argument(
        "--port", type=str, default="/dev/ttyUSB0",
        help="Serial port path (e.g. /dev/ttyUSB0, COM3). Default: /dev/ttyUSB0"
    )
    parser.add_argument(
        "--baud", type=int, default=19200,
        help="Baud rate for Modbus communication. Default: 19200"
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="Run in simulation/mock mode (no physical hardware required)"
    )
    parser.add_argument(
        "--safety-limit", type=float, default=55.0,
        help="Software safety feedback force threshold in Newtons (N). Default: 55.0 N"
    )
    parser.add_argument(
        "--dev", action="store_true",
        help="Run in frontend development mode (connects to Vite dev server)"
    )
    parser.add_argument(
        "--list-ports", action="store_true",
        help="List available serial ports and exit"
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
        parser.error(
            f"--safety-limit must be between 1.0 and 60.0 N (got {args.safety_limit})"
        )

    logger.info("Initializing Wavedriver Web Dashboard (Mock Mode: %s)", args.mock)

    controller = MotorController(use_mock=args.mock)

    safety_mN = int(args.safety_limit * 1000.0)
    controller.send_command("set_safety_limit", limit_mN=safety_mN)

    controller.start(port=args.port, baud=args.baud)

    api = WebviewAPI(controller=controller, initial_safety_limit_N=args.safety_limit)

    if args.dev:
        url = "http://localhost:5173"
    else:
        _rebuild_frontend_if_stale()
        build_dir = Path(__file__).resolve().parent / "web" / "dist" / "index.html"
        if not build_dir.exists():
            logger.error("Compiled frontend not found at %s. Run 'npm run build' first.", build_dir)
            controller.stop()
            sys.exit(1)
        url = str(build_dir)

    logger.info("Opening desktop UI window targeting: %s", url)

    window = webview.create_window(
        title="Wavedriver Orca 6 Dashboard",
        url=url,
        js_api=api,
        width=1000,
        height=720,
        min_size=(900, 650),
        background_color="#0d0e15"
    )
    api.set_window(window)

    try:
        webview.start()
    finally:
        logger.info("Shutting down motor controller...")
        controller.stop()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
