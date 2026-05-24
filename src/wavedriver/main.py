"""
Wavedriver CLI and Initialization Entry Point.

This module provides the main entry point to parse command-line arguments,
configure initial safety limits, initialize the motor controller, and start the Textual
Terminal User Interface (TUI) for interactive pleasure pattern playback.
"""

import argparse
import sys
from wavedriver.motor_controller import MotorController
from wavedriver.ui import WavedriverApp

def main():
    """Parses command-line arguments, initializes safety limits, and runs the Wavedriver TUI application."""
    parser = argparse.ArgumentParser(
        description="Wavedriver: TUI Controller for Iris Dynamics Orca 6 Linear Motor"
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
        "--list-ports",
        action="store_true",
        help="List available serial ports and exit"
    )

    args = parser.parse_args()

    if not (1.0 <= args.safety_limit <= 60.0):
        parser.error(
            f"--safety-limit must be between 1.0 and 60.0 N "
            f"(got {args.safety_limit}; hardware limit is 60 N)"
        )

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

    print(f"Initializing Wavedriver (Mock Mode: {args.mock})...")

    # Create the controller
    controller = MotorController(use_mock=args.mock)

    # Configure safety threshold
    safety_mN = int(args.safety_limit * 1000.0)
    controller.send_command("set_safety_limit", limit_mN=safety_mN)

    # Start background control loop thread
    controller.start(port=args.port, baud=args.baud)

    # Create and run the Textual TUI
    app = WavedriverApp(controller=controller, safety_limit=args.safety_limit)
    try:
        app.run()
    finally:
        # Ensure motor controller stops and cleans up
        print("Shutting down motor controller...")
        controller.stop()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()
