// Client-side mock of the Wavedriver PyWebView Python API
class MockWebviewAPI {
  constructor() {
    this.presets = {};
    this.session = { safety_force_n: 55, max_session_s: 0 };
    this.history = [];
    
    this.state = 'CONNECTED';
    this.paused = false;
    this.calibrated_length_um = 0;
    this.position_um = 75000;
    this.force_mN = 250;
    this.current_pattern_name = '';
    this.safety_force_limit_mN = 55000;
    this.session_elapsed_s = 0;
    
    // Start internal simulation clock for telemetry
    this._interval = setInterval(() => this._tick(), 50);
  }

  _tick() {
    if (this.state === 'CALIBRATING') {
      this.position_um -= 5000;
      if (this.position_um <= 10000) {
        this.position_um = 10000;
        this.state = 'CALIBRATED_IDLE';
        this.calibrated_length_um = 150000;
      }
    } else if (this.state === 'RUNNING' && !this.paused) {
      this.session_elapsed_s += 0.05;
      const angle = (Date.now() / 1000) * 2 * Math.PI;
      this.position_um = 75000 + Math.sin(angle) * 30000;
      this.force_mN = 1000 + Math.sin(angle * 2) * 500;
    }
  }

  async load_session() {
    return this.session;
  }

  async save_session(data) {
    this.session = { ...this.session, ...data };
    return { success: true };
  }

  async load_presets() {
    return this.presets;
  }

  async save_presets(data) {
    this.presets = data;
    return { success: true };
  }

  async load_session_history() {
    return this.history;
  }

  async save_session_history(record) {
    this.history.unshift({ ...record, timestamp: new Date().toISOString() });
    return { success: true };
  }

  _getDisplayState() {
    switch (this.state) {
      case 'UNCONNECTED': return 'Unconnected';
      case 'CONNECTING': return 'Connecting';
      case 'CONNECTED': return 'Connected';
      case 'CALIBRATING': return 'Calibrating';
      case 'CALIBRATED_IDLE': return 'Calibrated & Idle';
      case 'RUNNING': return 'Running';
      case 'ESTOP': return 'Estop';
      case 'ERROR': return 'Error';
      default: return this.state;
    }
  }

  async get_telemetry() {
    return {
      state: this._getDisplayState(),
      state_enum: this.state,
      error_msg: this.state === 'ESTOP' ? 'Emergency Stop Triggered' : '',
      position_um: Math.round(this.position_um),
      force_mN: Math.round(this.force_mN),
      speed_mm_s: this.state === 'RUNNING' ? 120 : 0,
      temperature_C: 32.5,
      voltage_mV: 24000,
      power_W: 15.2,
      errors_bitmask: 0,
      calibrated_length_um: this.calibrated_length_um,
      max_feedback_force_mN: this.safety_force_limit_mN,
      session_elapsed_s: Math.round(this.session_elapsed_s),
      session_remaining_s: null,
      paused: this.paused,
      use_mock: true,
      simulation_reason: "Mock UI mode",
      temp_warning: false,
      current_pattern_name: this.current_pattern_name,
      event_log: [],
    };
  }

  async send_command(cmd, args = {}) {
    console.log(`Mock API received command: ${cmd}`, args);
    switch (cmd) {
      case 'start_calibration':
        this.state = 'CALIBRATING';
        this.position_um = 75000;
        break;
      case 'start_pattern':
        this.state = 'RUNNING';
        this.current_pattern_name = args.pattern_name || 'Wave';
        break;
      case 'soft_stop':
        this.state = 'CALIBRATED_IDLE';
        break;
      case 'pause_pattern':
        this.paused = true;
        break;
      case 'resume_pattern':
        this.paused = false;
        break;
      case 'estop':
        this.state = 'ESTOP';
        break;
      case 'clear_estop':
        this.state = this.calibrated_length_um > 0 ? 'CALIBRATED_IDLE' : 'CONNECTED';
        break;
      case 'set_safety_limit':
        this.safety_force_limit_mN = args.limit_mN || 55000;
        break;
      default:
        break;
    }
    return { success: true };
  }

  async quit_application() {
    console.log("Mock API quit_application");
    return { success: true };
  }

  async list_ports() {
    return [
      { device: "mock", description: "Virtual Simulation Motor (mock)" },
      { device: "/dev/ttyUSB0", description: "Orca 6 Linear Actuator (ttyUSB0)" },
      { device: "/dev/ttyUSB1", description: "Orca 6 Linear Actuator (ttyUSB1)" }
    ];
  }

  async connect_port(port) {
    console.log(`Mock API reconnecting to port: ${port}`);
    this.port = port;
    return { success: true };
  }
}

const isRealPywebview = typeof window !== 'undefined' && (
  window.location.search.includes('platform=pywebview') ||
  window.navigator.userAgent.includes('pywebview')
);

if (typeof window !== 'undefined' && !window.pywebview && !isRealPywebview) {
  window.pywebview = {
    api: new MockWebviewAPI()
  };
  // Dispatch pywebviewready event
  setTimeout(() => {
    window.dispatchEvent(new Event('pywebviewready'));
  }, 10);
}
export default MockWebviewAPI;
