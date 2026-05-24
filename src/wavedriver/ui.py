import json
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import Header, Footer, Label, Button, ProgressBar, Static, Select
from textual.binding import Binding
from textual.screen import ModalScreen

from wavedriver.motor_controller import MotorController, ControllerState
from wavedriver import patterns

SESSION_FILE = Path.home() / ".config" / "wavedriver" / "session.json"
PRESETS_FILE = Path.home() / ".config" / "wavedriver" / "presets.json"

_PATTERN_OPTIONS = [
    ("Wave — smooth & steady",       "Wave"),
    ("Realistic — natural feel",     "Realistic"),
    ("Thrust — deep & rhythmic",     "Thrust"),
    ("Pulse — intense bursts",       "Pulse"),
    ("Tease — playful & varied",     "Tease"),
    ("Escalate — builds over time",  "Escalate"),
    ("Edge — climbs then drops",     "Edge"),
]
_VALID_PATTERNS = {value for _, value in _PATTERN_OPTIONS}

_SAFETY_LIMIT_MIN_N = 5.0
_SAFETY_LIMIT_MAX_N = 60.0

_REALISTIC_RATIOS = [2.5, 3.5, 5.0]

_SESSION_MIGRATIONS = {
    "Sine Wave":       "Wave",
    "Chaos":           "Tease",
    "Haptic Spring":   "Wave",
    "Slider-Crank":    "Realistic",
    "Slider-Crank-2.5": "Realistic",
    "Slider-Crank-3.5": "Realistic",
    "Slider-Crank-5.0": "Realistic",
}


# ── Modal screens ─────────────────────────────────────────────────────────────

class StartupScreen(ModalScreen):
    """A welcome and setup dialog presented to the user on startup.

    Provides options to resume the last cached calibration/session, initiate a fresh
    calibration cycle (recommended if the device has been re-mounted), or exit.
    """

    CSS = """
    StartupScreen {
        align: center middle;
    }

    #startup-dialog {
        background: #1e1e2e;
        border: double #cba6f7;
        padding: 2 4;
        width: 68;
        height: auto;
    }

    #startup-title {
        color: #f9e2af;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    #startup-body {
        color: #cdd6f4;
        margin-bottom: 2;
    }

    #startup-buttons {
        align: center middle;
        height: 3;
    }

    #startup-buttons Button {
        margin: 0 1;
        min-width: 20;
    }

    #btn-resume {
        background: #a6e3a1;
        color: #11111b;
        text-style: bold;
    }

    #btn-resume:hover {
        background: #94e2d5;
    }

    #btn-calibrate-startup {
        background: #89b4fa;
        color: #11111b;
        text-style: bold;
    }

    #btn-calibrate-startup:hover {
        background: #74c7ec;
    }

    #btn-quit-modal {
        background: #45475a;
        color: #cdd6f4;
    }

    #btn-quit-modal:hover {
        background: #585b70;
    }
    """

    def __init__(self, has_saved_cal: bool) -> None:
        super().__init__()
        self._has_saved_cal = has_saved_cal

    def compose(self) -> ComposeResult:
        with Vertical(id="startup-dialog"):
            yield Label("Welcome to Wavedriver", id="startup-title")
            if self._has_saved_cal:
                yield Label(
                    "Your last session is saved and ready to resume.\n\n"
                    "Choose Resume to pick up right where you left off,\n"
                    "or Recalibrate if you've remounted or repositioned the device.",
                    id="startup-body",
                )
                with Horizontal(id="startup-buttons"):
                    yield Button("Resume Session",  id="btn-resume")
                    yield Button("Recalibrate",      id="btn-calibrate-startup")
                    yield Button("Quit",             id="btn-quit-modal")
            else:
                yield Label(
                    "Before first use the device needs to measure its full range of motion.\n\n"
                    "During setup the shaft will move slowly to one end, then the other,\n"
                    "and return to the center position. This takes about 30 seconds.\n\n"
                    "Make sure the path is completely clear before continuing.",
                    id="startup-body",
                )
                with Horizontal(id="startup-buttons"):
                    yield Button("Set Up Device",  id="btn-calibrate-startup")
                    yield Button("Quit",            id="btn-quit-modal")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-resume":
            self.dismiss("resume")
        elif event.button.id == "btn-calibrate-startup":
            self.dismiss("recalibrate")
        else:
            self.dismiss("quit")


class ConfirmScreen(ModalScreen):
    """A modal double-check dialog asking the user to confirm high-impact actions.

    For example, used when confirming that starting calibration will stop the current running session.
    """

    CSS = """
    ConfirmScreen {
        align: center middle;
    }

    #confirm-dialog {
        background: #1e1e2e;
        border: double #f9e2af;
        padding: 2 4;
        width: 60;
        height: auto;
    }

    #confirm-body {
        color: #cdd6f4;
        margin-bottom: 2;
    }

    #confirm-buttons {
        align: center middle;
        height: 3;
    }

    #confirm-buttons Button {
        margin: 0 1;
        min-width: 16;
    }

    #btn-yes {
        background: #f9e2af;
        color: #11111b;
        text-style: bold;
    }

    #btn-yes:hover {
        background: #fab387;
    }

    #btn-no {
        background: #45475a;
        color: #cdd6f4;
    }

    #btn-no:hover {
        background: #585b70;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._message, id="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Button("Confirm", id="btn-yes")
                yield Button("Cancel",  id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")


# ── TelemetryBox widget ────────────────────────────────────────────────────────

class TelemetryBox(Static):
    """A custom widget grid cell used in the Telemetry Dashboard.

    Displays a specific motor or session state parameter label, its current value, 
    and its optional measurement unit.
    """

    def __init__(self, label: str, value: str, unit: str = "",
                 id: str = None, classes: str = ""):
        super().__init__(id=id, classes=classes)
        self.label_text = label
        self.value_text = value
        self.unit_text  = unit

    def compose(self) -> ComposeResult:
        yield Label(self.label_text, classes="box-title")
        with Horizontal():
            yield Label(self.value_text, id="value-lbl", classes="box-value")
            yield Label(self.unit_text,  classes="box-unit")

    def update_value(self, value: str) -> None:
        self.query_one("#value-lbl").update(value)


# ── Main application ───────────────────────────────────────────────────────────

class WavedriverApp(App):
    """The Wavedriver Textual TUI Application.

    Manages user layouts, maps keyboard inputs to control commands, handles preset persistence, 
    and drives periodic dashboard refreshes showing motor speed, stroke, and safety limits.
    """

    CSS = """
    Screen {
        background: #111116;
        color: #e2e8f0;
    }

    #app-container {
        padding: 0 1;
        height: 100%;
        overflow-y: auto;
    }

    .section-title {
        background: #1e1e2e;
        color: #cba6f7;
        text-align: center;
        padding: 0 1;
        margin-bottom: 0;
        border: tall #313244;
        text-style: bold;
    }

    #telemetry-grid {
        grid-size: 4 2;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-rows: 4 4;
        margin-bottom: 0;
        height: 10;
    }

    #debug-grid {
        grid-size: 4 1;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-rows: 4;
        margin-bottom: 0;
        height: 5;
        display: none;
    }

    TelemetryBox {
        background: #181825;
        border: solid #313244;
        padding: 0 1;
        align: center middle;
    }

    .box-title {
        color: #89b4fa;
        margin-bottom: 0;
    }

    .box-value {
        text-style: bold;
        color: #f5c2e7;
    }

    .box-unit {
        color: #a6adc8;
        margin-left: 1;
        margin-top: 0;
    }

    #visual-shaft-panel {
        background: #181825;
        border: solid #313244;
        padding: 0 1;
        margin-bottom: 1;
        height: 5;
    }

    #shaft-title {
        color: #f9e2af;
        text-style: bold;
        margin-bottom: 0;
    }

    #shaft-range-label {
        color: #a6adc8;
        margin-top: 0;
    }

    #control-panel {
        background: #181825;
        border: solid #313244;
        padding: 1 2;
        height: auto;
    }

    #mode-select-row {
        height: 3;
    }

    .ctrl-label {
        text-style: bold;
        color: #a6e3a1;
        margin-top: 1;
    }

    #estop-banner {
        background: #f38ba8;
        color: #11111b;
        text-align: center;
        text-style: bold;
        padding: 1;
        border: double #e64553;
        margin-bottom: 1;
        display: none;
    }

    #error-banner {
        background: #fab387;
        color: #11111b;
        text-align: center;
        text-style: bold;
        padding: 1;
        border: double #fe640b;
        margin-bottom: 1;
        display: none;
    }

    .success-text { color: #a6e3a1; }
    .warning-text { color: #f9e2af; }
    .danger-text  { color: #f38ba8; }
    .info-text    { color: #89b4fa; }

    Button {
        margin-right: 1;
        background: #313244;
        color: #cdd6f4;
        border: none;
    }

    Button:hover {
        background: #45475a;
    }

    #btn-estop {
        background: #f38ba8;
        color: #11111b;
        text-style: bold;
    }

    #btn-estop:hover {
        background: #e64553;
    }

    #btn-clear-estop {
        background: #a6e3a1;
        color: #11111b;
        text-style: bold;
    }

    #btn-clear-estop:hover {
        background: #94e2d5;
    }

    .control-buttons-row {
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("space",  "estop",          "EMERGENCY STOP",  priority=True),
        Binding("z",      "auto_zero",       "Calibrate",       priority=True),
        Binding("p",      "pause_resume",    "Pause / Resume"),
        Binding("up",     "param_up",        "Speed +"),
        Binding("down",   "param_down",      "Speed -"),
        Binding("right",  "param_right",     "Stroke / Param +"),
        Binding("left",   "param_left",      "Stroke / Param -"),
        Binding("=",      "intensity_up",    "Intensity +10%"),
        Binding("-",      "intensity_down",  "Intensity -10%"),
        Binding("]",      "limit_up",        "Safety +5 N"),
        Binding("[",      "limit_down",      "Safety -5 N"),
        Binding("d",      "toggle_debug",    "Debug Info"),
        Binding("c",      "clear_estop",     "Clear E-STOP"),
        Binding("1",      "recall_preset(0)", "Preset 1"),
        Binding("2",      "recall_preset(1)", "Preset 2"),
        Binding("3",      "recall_preset(2)", "Preset 3"),
        Binding("4",      "recall_preset(3)", "Preset 4"),
        Binding("5",      "recall_preset(4)", "Preset 5"),
        Binding("ctrl+1", "save_preset(0)",  "Save Preset 1"),
        Binding("ctrl+2", "save_preset(1)",  "Save Preset 2"),
        Binding("ctrl+3", "save_preset(2)",  "Save Preset 3"),
        Binding("ctrl+4", "save_preset(3)",  "Save Preset 4"),
        Binding("ctrl+5", "save_preset(4)",  "Save Preset 5"),
        Binding("q",      "quit",            "Quit"),
    ]

    def __init__(self, controller: MotorController, safety_limit: float = 55.0,
                 max_session_s: int = 1800) -> None:
        """Initializes the TUI application state and configures default settings.

        Args:
            controller (MotorController): The active background motor controller coordinator.
            safety_limit (float): Default software feedback force threshold in Newtons (default: 55 N).
            max_session_s (int): Session auto-shutoff duration in seconds (default: 1800s / 30m).
        """
        super().__init__()
        self.controller = controller

        self.pattern_name        = "Wave"
        self.frequency_hz        = 1.0
        self.stroke_length_mm    = 50.0
        self.safety_force_N      = safety_limit
        self.rod_ratio           = 2.5
        self.intensity_pct       = 50.0
        self.escalate_duration_s = 300.0
        self.edge_period_s       = 60.0
        self.debug_telemetry     = False
        self.max_session_s       = max_session_s
        self._paused             = False
        self._saved_cal_um       = 0
        self.presets: list       = [None] * 5

        self._load_session()
        self._load_presets()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_session(self) -> None:
        """Loads cached settings (selected pattern, speeds, strokes, limits) from the local user session file."""
        try:
            if SESSION_FILE.exists():
                data = json.loads(SESSION_FILE.read_text())
                loaded = _SESSION_MIGRATIONS.get(
                    data.get("pattern_name", self.pattern_name),
                    data.get("pattern_name", self.pattern_name),
                )
                if loaded in _VALID_PATTERNS:
                    self.pattern_name = loaded
                self.frequency_hz        = max(0.1,   min(3.0,    float(data.get("frequency_hz",        self.frequency_hz))))
                self.stroke_length_mm    = max(10.0,  min(150.0,  float(data.get("stroke_length_mm",    self.stroke_length_mm))))
                self.rod_ratio           = max(2.5,   min(5.0,    float(data.get("rod_ratio",           self.rod_ratio))))
                self.intensity_pct       = max(10.0,  min(100.0,  float(data.get("intensity_pct",       self.intensity_pct))))
                self.escalate_duration_s = max(30.0,  min(3600.0, float(data.get("escalate_duration_s", self.escalate_duration_s))))
                self.edge_period_s       = max(10.0,  min(600.0,  float(data.get("edge_period_s",       self.edge_period_s))))
                self._saved_cal_um       = int(data.get("calibrated_length_um", 0))
        except Exception:
            pass

    def _save_session(self) -> None:
        """Saves current session settings and measured calibration range to the local user session file."""
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            tel    = self.controller.get_telemetry()
            cal_um = tel.get("calibrated_length_um", 0) or self._saved_cal_um
            SESSION_FILE.write_text(json.dumps({
                "pattern_name":         self.pattern_name,
                "frequency_hz":         self.frequency_hz,
                "stroke_length_mm":     self.stroke_length_mm,
                "rod_ratio":            self.rod_ratio,
                "intensity_pct":        self.intensity_pct,
                "escalate_duration_s":  self.escalate_duration_s,
                "edge_period_s":        self.edge_period_s,
                "calibrated_length_um": cal_um,
            }))
        except Exception:
            pass

    def _load_presets(self) -> None:
        """Loads five slots of saved user configurations from the local presets file."""
        try:
            if PRESETS_FILE.exists():
                data = json.loads(PRESETS_FILE.read_text())
                for i in range(5):
                    slot = data.get(str(i))
                    if isinstance(slot, dict):
                        self.presets[i] = slot
        except Exception:
            pass

    def _save_presets(self) -> None:
        """Persists the current slots of user configurations to the local presets file."""
        try:
            PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
            PRESETS_FILE.write_text(json.dumps(
                {str(i): self.presets[i] for i in range(5)}
            ))
        except Exception:
            pass

    def _current_preset_dict(self) -> dict:
        """Helper to create a serialized settings dictionary from the current active configuration."""
        return {
            "pattern_name":        self.pattern_name,
            "frequency_hz":        self.frequency_hz,
            "stroke_length_mm":    self.stroke_length_mm,
            "intensity_pct":       self.intensity_pct,
            "rod_ratio":           self.rod_ratio,
            "escalate_duration_s": self.escalate_duration_s,
            "edge_period_s":       self.edge_period_s,
        }

    def _apply_preset(self, slot: dict) -> None:
        """Applies a configuration dictionary slot, updating current active parameters and pattern playback."""
        loaded = _SESSION_MIGRATIONS.get(
            slot.get("pattern_name", self.pattern_name),
            slot.get("pattern_name", self.pattern_name),
        )
        self.pattern_name        = loaded if loaded in _VALID_PATTERNS else "Wave"
        self.frequency_hz        = max(0.1,  min(3.0,    float(slot.get("frequency_hz",        self.frequency_hz))))
        self.stroke_length_mm    = max(10.0, min(150.0,  float(slot.get("stroke_length_mm",    self.stroke_length_mm))))
        self.intensity_pct       = max(10.0, min(100.0,  float(slot.get("intensity_pct",       self.intensity_pct))))
        self.rod_ratio           = max(2.5,  min(5.0,    float(slot.get("rod_ratio",           self.rod_ratio))))
        self.escalate_duration_s = max(30.0, min(3600.0, float(slot.get("escalate_duration_s", self.escalate_duration_s))))
        self.edge_period_s       = max(10.0, min(600.0,  float(slot.get("edge_period_s",       self.edge_period_s))))
        try:
            self.query_one("#sel-pattern", Select).value = self.pattern_name
        except Exception:
            pass
        self._apply_intensity()
        self._update_pattern()

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="app-container"):
            yield Static("!!! EMERGENCY STOP ACTIVE !!!", id="estop-banner")
            yield Static("", id="error-banner")

            yield Label("STATUS", classes="section-title")
            with Grid(id="telemetry-grid"):
                # Row 1 — live readings
                yield TelemetryBox("State",       "Unconnected",                   id="box-state")
                yield TelemetryBox("Position",    "0.0",    unit="mm",             id="box-pos")
                yield TelemetryBox("Resistance",  "0",      unit="%",              id="box-resistance")
                yield TelemetryBox("Speed",       "1",      unit="/ 10",           id="box-speed")
                # Row 2 — current settings
                yield TelemetryBox("Intensity =/-", f"{self.intensity_pct:.0f}", unit="%", id="box-intensity")
                yield TelemetryBox("Stroke ←→",  f"{self.stroke_length_mm:.0f}", unit="mm", id="box-stroke")
                yield TelemetryBox("Safety \\[/]", f"{self.safety_force_N:.0f}",   unit="N",  id="box-safety")
                yield TelemetryBox("Session",    "0:00",                          id="box-session")

            # Debug row — hidden until D is pressed
            with Grid(id="debug-grid"):
                yield TelemetryBox("Power",   "0",   unit="W",   id="box-power")
                yield TelemetryBox("Temp",    "0",   unit="°C",  id="box-temp")
                yield TelemetryBox("Voltage", "0.0", unit="V",   id="box-volt")
                yield TelemetryBox("Param",   "—",               id="box-param")

            with Vertical(id="visual-shaft-panel"):
                yield Label("Shaft Position", id="shaft-title")
                yield ProgressBar(total=100, show_bar=True, show_percentage=False, id="shaft-progress")
                yield Label("0.0 mm  (0 – 150 mm)", id="shaft-range-label")

            yield Label("CONTROLS", classes="section-title")
            with Vertical(id="control-panel"):
                with Horizontal(id="mode-select-row"):
                    yield Label("Pattern: ", classes="ctrl-label")
                    yield Select(options=_PATTERN_OPTIONS, value=self.pattern_name, id="sel-pattern")
                with Horizontal(classes="control-buttons-row"):
                    yield Button("Calibrate [Z]",         id="btn-calibrate")
                    yield Button("Start",                  id="btn-start",      classes="info-text")
                    yield Button("Stop",                   id="btn-stop")
                    yield Button("CLEAR E-STOP [C]",       id="btn-clear-estop")
                    yield Button("EMERGENCY STOP [Space]", id="btn-estop")
        yield Footer()

    def on_mount(self) -> None:
        """Mount event handler. Initiates the telemetry refresh interval and displays the startup setup modal."""
        self.set_interval(0.05, self.update_telemetry)
        if self.max_session_s > 0:
            self.controller.send_command("set_max_session", max_s=self.max_session_s)
        self._apply_intensity()
        self.push_screen(StartupScreen(self._saved_cal_um > 0), self._on_startup_choice)

    def _on_startup_choice(self, choice: str) -> None:
        if choice == "resume":
            self.controller.send_command("load_calibration", length_um=self._saved_cal_um)
            self.notify("Resumed from last session.")
        elif choice == "recalibrate":
            self.controller.send_command("start_calibration")
            self.notify("Setting up — please wait while the device calibrates...")
        else:
            self._save_session()
            self._save_presets()
            self.exit()

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sel-pattern":
            self.pattern_name = str(event.value)
            if self.controller.get_telemetry().get("paused", False):
                self.controller.send_command("resume_pattern")
            self._paused = False
            self._update_pattern()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-estop":
            self.action_estop()
        elif button_id == "btn-clear-estop":
            self.action_clear_estop()
        elif button_id == "btn-calibrate":
            self.action_auto_zero()
        elif button_id == "btn-start":
            self._update_pattern(force=True)
            self.notify("Starting...")
        elif button_id == "btn-stop":
            self.controller.send_command("soft_stop")
            self.notify("Stopping...")

    # ── Telemetry update ──────────────────────────────────────────────────────

    def update_telemetry(self) -> None:
        tel        = self.controller.get_telemetry()
        state_enum = tel["state_enum"]

        # Banners
        if state_enum == ControllerState.ESTOP:
            self.query_one("#estop-banner").display = True
            self.query_one("#error-banner").display  = False
        elif state_enum == ControllerState.ERROR:
            self.query_one("#estop-banner").display = False
            error_banner = self.query_one("#error-banner", Static)
            error_banner.update(f"ERROR: {tel['error_msg']}")
            error_banner.display = True
        else:
            self.query_one("#estop-banner").display = False
            self.query_one("#error-banner").display  = False

        # Mirror pause flag from controller
        self._paused = tel.get("paused", False)

        # State box
        if state_enum == ControllerState.RUNNING and self._paused:
            display_state = "Paused"
        else:
            display_state = tel["state"]
        box_state = self.query_one("#box-state", TelemetryBox)
        box_state.update_value(display_state)
        state_lbl = box_state.query_one("#value-lbl")
        state_lbl.remove_class("danger-text", "warning-text", "success-text", "info-text")
        if state_enum in (ControllerState.ESTOP, ControllerState.ERROR):
            state_lbl.add_class("danger-text")
        elif state_enum in (ControllerState.CALIBRATING_RETRACT,
                            ControllerState.CALIBRATING_EXTEND,
                            ControllerState.CALIBRATING_CENTER):
            state_lbl.add_class("warning-text")
        elif state_enum == ControllerState.RUNNING:
            state_lbl.add_class("success-text")
        else:
            state_lbl.add_class("info-text")

        # Position
        pos_mm = tel["position_um"] / 1000.0
        self.query_one("#box-pos", TelemetryBox).update_value(f"{pos_mm:.1f}")

        # Resistance % (force vs safety limit)
        force_abs  = abs(tel["force_mN"])
        limit_mN   = tel["max_feedback_force_mN"]
        resist_pct = min(100, int(force_abs / limit_mN * 100)) if limit_mN > 0 else 0
        resist_box = self.query_one("#box-resistance", TelemetryBox)
        resist_box.update_value(str(resist_pct))
        resist_lbl = resist_box.query_one("#value-lbl")
        resist_lbl.remove_class("danger-text", "warning-text")
        if resist_pct >= 90:
            resist_lbl.add_class("danger-text")
        elif resist_pct >= 70:
            resist_lbl.add_class("warning-text")

        # Speed 1–10 mapped from frequency range 0.1–3.0 Hz
        speed_1_10 = max(1, min(10, round((self.frequency_hz - 0.1) / 2.9 * 9 + 1)))
        self.query_one("#box-speed", TelemetryBox).update_value(str(speed_1_10))

        # Row 2
        self.query_one("#box-intensity", TelemetryBox).update_value(f"{self.intensity_pct:.0f}")
        self.query_one("#box-stroke",    TelemetryBox).update_value(f"{self.stroke_length_mm:.0f}")
        self.query_one("#box-safety",    TelemetryBox).update_value(f"{limit_mN / 1000.0:.0f}")

        elapsed    = int(tel.get("session_elapsed_s", 0) or 0)
        mins, secs = divmod(elapsed, 60)
        self.query_one("#box-session", TelemetryBox).update_value(f"{mins}:{secs:02d}")

        # Debug row
        self.query_one("#box-power",   TelemetryBox).update_value(f"{tel['power_W']}")
        self.query_one("#box-temp",    TelemetryBox).update_value(f"{tel['temperature_C']}")
        self.query_one("#box-volt",    TelemetryBox).update_value(f"{tel['voltage_mV'] / 1000.0:.1f}")

        if self.pattern_name == "Realistic":
            param_str = f"{self.rod_ratio:.1f}x"
        elif self.pattern_name == "Escalate":
            param_str = f"{self.escalate_duration_s:.0f}s"
        elif self.pattern_name == "Edge":
            param_str = f"{self.edge_period_s:.0f}s"
        else:
            param_str = f"{self.frequency_hz:.1f}Hz"
        self.query_one("#box-param", TelemetryBox).update_value(param_str)

        # Shaft visualizer
        cal_len = tel["calibrated_length_um"] if tel["calibrated_length_um"] > 0 else 150000.0
        cal_mm  = cal_len / 1000.0
        pos_pct = max(0.0, min(100.0, (tel["position_um"] / cal_len) * 100.0))
        self.query_one("#shaft-progress",   ProgressBar).progress = pos_pct
        self.query_one("#shaft-range-label", Label).update(
            f"{pos_mm:.1f} mm  (0 – {cal_mm:.0f} mm)"
        )

    # ── Pattern dispatch ──────────────────────────────────────────────────────

    def _apply_intensity(self) -> None:
        self.controller.send_command("set_intensity", intensity=self.intensity_pct / 100.0)

    def _update_pattern(self, force: bool = False) -> None:
        tel = self.controller.get_telemetry()
        if not force and tel["state_enum"] != ControllerState.RUNNING:
            return

        stroke_um = int(self.stroke_length_mm * 1000.0)
        params    = {"stroke_length_um": stroke_um, "frequency_hz": self.frequency_hz}

        if self.pattern_name == "Wave":
            pattern_func = patterns.wave_pattern
        elif self.pattern_name == "Realistic":
            pattern_func = patterns.realistic_pattern
            params["rod_ratio"] = self.rod_ratio
        elif self.pattern_name == "Thrust":
            pattern_func = patterns.thrust_pattern
        elif self.pattern_name == "Pulse":
            pattern_func = patterns.pulse_pattern
        elif self.pattern_name == "Tease":
            pattern_func = patterns.tease_pattern
        elif self.pattern_name == "Escalate":
            pattern_func = patterns.escalate_pattern
            params["escalate_duration_s"] = self.escalate_duration_s
        elif self.pattern_name == "Edge":
            pattern_func = patterns.edge_pattern
            params["edge_period_s"] = self.edge_period_s
        else:
            return

        self.controller.send_command("start_pattern", pattern_func=pattern_func, params=params)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_estop(self) -> None:
        self.controller.send_command("estop", reason="Emergency Stop Key Pressed")
        self.notify("EMERGENCY STOP TRIGGERED", severity="error")

    def action_auto_zero(self) -> None:
        tel = self.controller.get_telemetry()
        if tel["state_enum"] == ControllerState.RUNNING:
            self.push_screen(
                ConfirmScreen(
                    "Stop the current session and recalibrate?\n\n"
                    "The shaft will move to both ends and return to center.\n"
                    "Make sure the path is completely clear."
                ),
                self._on_recal_confirmed,
            )
        else:
            self._do_calibration()

    def _on_recal_confirmed(self, ok: bool) -> None:
        if ok:
            self._do_calibration()

    def _do_calibration(self) -> None:
        self.controller.send_command("start_calibration")
        self.notify("Calibrating — please wait...")

    def action_pause_resume(self) -> None:
        if self.controller.get_telemetry()["state_enum"] != ControllerState.RUNNING:
            return
        if self._paused:
            self.controller.send_command("resume_pattern")
            self._paused = False
            self.notify("Resumed")
        else:
            self.controller.send_command("pause_pattern")
            self._paused = True
            self.notify("Paused — press P to resume")

    def action_intensity_up(self) -> None:
        self.intensity_pct = min(100.0, self.intensity_pct + 10.0)
        self._apply_intensity()
        self.notify(f"Intensity: {self.intensity_pct:.0f}%")

    def action_intensity_down(self) -> None:
        self.intensity_pct = max(10.0, self.intensity_pct - 10.0)
        self._apply_intensity()
        self.notify(f"Intensity: {self.intensity_pct:.0f}%")

    def action_toggle_debug(self) -> None:
        self.debug_telemetry = not self.debug_telemetry
        self.query_one("#debug-grid").display = self.debug_telemetry

    def action_param_up(self) -> None:
        self.frequency_hz = min(3.0, round(self.frequency_hz + 0.1, 1))
        self.notify(f"Speed: {self.frequency_hz:.1f} Hz  ({int(self.frequency_hz * 60)} SPM)")
        self._update_pattern()

    def action_param_down(self) -> None:
        self.frequency_hz = max(0.1, round(self.frequency_hz - 0.1, 1))
        self.notify(f"Speed: {self.frequency_hz:.1f} Hz  ({int(self.frequency_hz * 60)} SPM)")
        self._update_pattern()

    def action_param_right(self) -> None:
        if self.pattern_name == "Realistic":
            idx = min(range(len(_REALISTIC_RATIOS)),
                      key=lambda i: abs(_REALISTIC_RATIOS[i] - self.rod_ratio))
            self.rod_ratio = _REALISTIC_RATIOS[min(len(_REALISTIC_RATIOS) - 1, idx + 1)]
            self.notify(f"Realistic feel: {self.rod_ratio:.1f}x")
        else:
            tel     = self.controller.get_telemetry()
            max_len = (tel["calibrated_length_um"] / 1000.0
                       if tel["calibrated_length_um"] > 0 else 150.0)
            self.stroke_length_mm = min(max_len - 10.0, self.stroke_length_mm + 5.0)
            self.notify(f"Stroke: {self.stroke_length_mm:.0f} mm")
        self._update_pattern()

    def action_param_left(self) -> None:
        if self.pattern_name == "Realistic":
            idx = min(range(len(_REALISTIC_RATIOS)),
                      key=lambda i: abs(_REALISTIC_RATIOS[i] - self.rod_ratio))
            self.rod_ratio = _REALISTIC_RATIOS[max(0, idx - 1)]
            self.notify(f"Realistic feel: {self.rod_ratio:.1f}x")
        else:
            self.stroke_length_mm = max(10.0, self.stroke_length_mm - 5.0)
            self.notify(f"Stroke: {self.stroke_length_mm:.0f} mm")
        self._update_pattern()

    def action_limit_up(self) -> None:
        self.safety_force_N = min(_SAFETY_LIMIT_MAX_N, self.safety_force_N + 5.0)
        self.controller.send_command("set_safety_limit", limit_mN=int(self.safety_force_N * 1000))
        self.notify(f"Safety Limit: {self.safety_force_N:.0f} N")

    def action_limit_down(self) -> None:
        self.safety_force_N = max(_SAFETY_LIMIT_MIN_N, self.safety_force_N - 5.0)
        self.controller.send_command("set_safety_limit", limit_mN=int(self.safety_force_N * 1000))
        self.notify(f"Safety Limit: {self.safety_force_N:.0f} N")

    def action_recall_preset(self, slot: int) -> None:
        preset = self.presets[slot]
        if preset is None:
            self.notify(f"Preset {slot + 1} is empty", severity="warning")
            return
        self._apply_preset(preset)
        self.notify(f"Preset {slot + 1}: {preset.get('pattern_name', '?')}")

    def action_save_preset(self, slot: int) -> None:
        self.presets[slot] = self._current_preset_dict()
        self._save_presets()
        self.notify(f"Saved to Preset {slot + 1}")

    def action_clear_estop(self) -> None:
        self.controller.send_command("clear_estop")
        self.notify("E-STOP cleared. Recalibrate before resuming.")

    def action_quit(self) -> None:
        self._save_session()
        self._save_presets()
        self.exit()
