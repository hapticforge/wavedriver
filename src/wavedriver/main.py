"""
Wavedriver Web UI Launcher and PyWebView Bridge.

This module provides the main entry point to start the motor controller and
launches the PyWebView desktop app GUI, exposing a Python-to-JS bridge API.
It performs parameter validations and legacy migrations.
"""

import argparse
import sys
import os
import json
import webview
from pathlib import Path

from wavedriver.motor_controller import MotorController, ControllerState
from wavedriver import patterns

SESSION_FILE = Path.home() / ".config" / "wavedriver" / "session.json"
PRESETS_FILE = Path.home() / ".config" / "wavedriver" / "presets.json"

_VALID_PATTERNS = {"Wave", "Realistic", "Thrust", "Pulse", "Tease", "Escalate", "Edge"}

_SESSION_MIGRATIONS = {
    "Sine Wave":       "Wave",
    "Chaos":           "Tease",
    "Haptic Spring":   "Wave",
    "Slider-Crank":    "Realistic",
    "Slider-Crank-2.5": "Realistic",
    "Slider-Crank-3.5": "Realistic",
    "Slider-Crank-5.0": "Realistic",
}

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
            # Convert non-serializable Enum fields to string names
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
            # Map pattern_name string to pattern function
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
                else:
                    return {"success": False, "error": f"Unknown pattern name: {pattern_name}"}
                
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
        """Loads cached settings from local session file, performing migrations and clamping to safe ranges."""
        try:
            if SESSION_FILE.exists():
                data = json.loads(SESSION_FILE.read_text())
                
                # Perform pattern migrations
                pattern = data.get("pattern_name", "Wave")
                migrated_pattern = _SESSION_MIGRATIONS.get(pattern, pattern)
                if migrated_pattern in _VALID_PATTERNS:
                    pattern = migrated_pattern
                else:
                    pattern = "Wave"
                
                # Clamp fields to valid ranges
                frequency_hz = max(0.1, min(3.0, float(data.get("frequency_hz", 1.0))))
                stroke_length_mm = max(10.0, min(150.0, float(data.get("stroke_length_mm", 50.0))))
                rod_ratio = max(2.5, min(5.0, float(data.get("rod_ratio", 2.5))))
                intensity_pct = max(10.0, min(100.0, float(data.get("intensity_pct", 50.0))))
                escalate_duration_s = max(30.0, min(3600.0, float(data.get("escalate_duration_s", 300.0))))
                edge_period_s = max(10.0, min(600.0, float(data.get("edge_period_s", 60.0))))
                calibrated_length_um = int(data.get("calibrated_length_um", 0))
                
                return {
                    "pattern_name": pattern,
                    "frequency_hz": frequency_hz,
                    "stroke_length_mm": stroke_length_mm,
                    "rod_ratio": rod_ratio,
                    "intensity_pct": intensity_pct,
                    "escalate_duration_s": escalate_duration_s,
                    "edge_period_s": edge_period_s,
                    "calibrated_length_um": calibrated_length_um,
                }
        except Exception:
            pass
        
        # Fallback default configuration
        return {
            "pattern_name": "Wave",
            "frequency_hz": 1.0,
            "stroke_length_mm": 50.0,
            "rod_ratio": 2.5,
            "intensity_pct": 50.0,
            "escalate_duration_s": 300.0,
            "edge_period_s": 60.0,
            "calibrated_length_um": 0,
        }

    def save_session(self, session_data: dict) -> dict:
        """Saves current session settings to local session file."""
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Automatically mix in calibrated length from controller telemetry if not provided
            if "calibrated_length_um" not in session_data:
                tel = self.controller.get_telemetry()
                session_data["calibrated_length_um"] = tel.get("calibrated_length_um", 0)
                
            SESSION_FILE.write_text(json.dumps(session_data))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

def main():
    """Parses command-line arguments and launches the Wavedriver PyWebView app."""
    parser = argparse.ArgumentParser(
        description="Wavedriver: Graphical Dashboard for Iris Dynamics Orca 6 Linear Motor"
    )
    parser.add_argument(
        "--port",
        type=str,
        default="/dev/ttyUSB0",
        help="Serial port path (e.g. /dev/ttyUSB0, COM3). Default: /dev/ttyUSB0"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=19200,
        help="Baud rate for Modbus communication. Default: 19200"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in simulation/mock mode (no physical hardware required)"
    )
    parser.add_argument(
        "--safety-limit",
        type=float,
        default=55.0,
        help="Software safety feedback force threshold in Newtons (N). Default: 55.0 N"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in frontend development mode (connects to Vite dev server)"
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
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

    print(f"Initializing Wavedriver Web Dashboard (Mock Mode: {args.mock})...")

    # Create the controller
    controller = MotorController(use_mock=args.mock)

    # Configure safety threshold
    safety_mN = int(args.safety_limit * 1000.0)
    controller.send_command("set_safety_limit", limit_mN=safety_mN)

    # Start background control loop thread
    controller.start(port=args.port, baud=args.baud)

    # Instantiate API
    api = WebviewAPI(controller=controller, initial_safety_limit_N=args.safety_limit)

    # Set up web view source url
    if args.dev:
        url = "http://localhost:5173"
    else:
        # Resolve path to the compiled frontend build/index.html
        build_dir = Path(__file__).resolve().parent / "web" / "dist" / "index.html"
        if not build_dir.exists():
            print(f"Error: Compiled frontend not found at {build_dir}. Please build the web project first.")
            controller.stop()
            sys.exit(1)
        url = str(build_dir)

    print(f"Opening desktop UI window targeting: {url}")
    
    # Create pywebview window
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
        print("Shutting down motor controller...")
        controller.stop()
        print("Shutdown complete.")
        os._exit(0)

if __name__ == "__main__":
    main()
