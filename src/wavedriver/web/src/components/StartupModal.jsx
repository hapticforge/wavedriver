import { useState, useEffect, memo } from 'react';
import { Shield, Settings, Activity, CheckCircle } from 'lucide-react';

/**
 * Onboarding and guided calibration modal.
 * Steps: WELCOME -> CONNECT -> CALIBRATING -> COMPLETE
 */
export const StartupModal = memo(function StartupModal({ step, setStep, telemetry, onConnectAndCalibrate, onClose }) {
  const [safetyChecked, setSafetyChecked] = useState({
    power: false,
    path: false,
    estop: false,
  });
  
  const [ports, setPorts] = useState([]);
  const [selectedPort, setSelectedPort] = useState('');
  const [isLoadingPorts, setIsLoadingPorts] = useState(true);

  // Fetch serial ports on CONNECT step
  useEffect(() => {
    if (step !== 'CONNECT') return;
    
    let active = true;
    const fetchPorts = async () => {
      try {
        if (window.pywebview?.api?.list_ports) {
          const list = await window.pywebview.api.list_ports();
          if (active) {
            setPorts(list || []);
            if (list && list.length > 0) {
              setSelectedPort(list[0].device);
            } else {
              setSelectedPort('mock');
            }
            setIsLoadingPorts(false);
          }
        } else {
          setTimeout(fetchPorts, 100);
        }
      } catch (e) {
        console.error("Failed to fetch ports:", e);
        if (active) setIsLoadingPorts(false);
      }
    };
    fetchPorts();
    return () => { active = false; };
  }, [step]);

  // Monitor calibration progress
  useEffect(() => {
    if (step === 'CALIBRATING' && telemetry) {
      const isCalibrated = telemetry.state_enum === 'CALIBRATED_IDLE' && telemetry.calibrated_length_um > 0;
      if (isCalibrated) {
        setStep('COMPLETE');
      }
    }
  }, [telemetry, step, setStep]);

  const allSafetyChecked = safetyChecked.power && safetyChecked.path && safetyChecked.estop;

  const handleStartCalibration = async () => {
    setStep('CALIBRATING');
    onConnectAndCalibrate(selectedPort);
  };

  const getCalibStatusText = () => {
    switch (telemetry.state_enum) {
      case 'CALIBRATING_RETRACT':
        return 'Retracting shaft slowly to find the back end-stop...';
      case 'CALIBRATING_EXTEND':
        return 'Extending shaft slowly to find the front end-stop...';
      case 'CALIBRATING_CENTER':
        return 'Centering the shaft to ready position...';
      default:
        return 'Calibration initialized. Waiting for motor movements...';
    }
  };

  const getCalibProgressPercent = () => {
    switch (telemetry.state_enum) {
      case 'CALIBRATING_RETRACT':
        return 33;
      case 'CALIBRATING_EXTEND':
        return 66;
      case 'CALIBRATING_CENTER':
        return 90;
      default:
        return 10;
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-dialog" style={{ maxWidth: '520px' }}>
        
        {/* Step 1: Welcome & Safety Acknowledgement */}
        {step === 'WELCOME' && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
              <Shield className="text-cyan" size={28} />
              <h2 className="modal-title" style={{ margin: 0 }}>Safety Onboarding</h2>
            </div>
            
            <p className="modal-body">
              Wavedriver is a high-performance linear motor controller. Because the actuator moves with considerable force, safety acknowledgement is mandatory before startup.
            </p>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '8px', margin: '20px 0' }}>
              <label style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', marginBottom: '12px', cursor: 'pointer', fontSize: '0.9rem' }}>
                <input
                  type="checkbox"
                  style={{ marginTop: '3px' }}
                  checked={safetyChecked.power}
                  onChange={(e) => setSafetyChecked({ ...safetyChecked, power: e.target.checked })}
                />
                <span>I understand that this device is powered and can move with high force/velocity.</span>
              </label>

              <label style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', marginBottom: '12px', cursor: 'pointer', fontSize: '0.9rem' }}>
                <input
                  type="checkbox"
                  style={{ marginTop: '3px' }}
                  checked={safetyChecked.path}
                  onChange={(e) => setSafetyChecked({ ...safetyChecked, path: e.target.checked })}
                />
                <span>I have cleared the shaft travel path of all obstacles, clothing, or fingers.</span>
              </label>

              <label style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', cursor: 'pointer', fontSize: '0.9rem' }}>
                <input
                  type="checkbox"
                  style={{ marginTop: '3px' }}
                  checked={safetyChecked.estop}
                  onChange={(e) => setSafetyChecked({ ...safetyChecked, estop: e.target.checked })}
                />
                <span>I know that pressing the <strong>Spacebar</strong> instantly triggers an Emergency Stop.</span>
              </label>
            </div>

            <div className="modal-buttons">
              <button
                className="btn btn-primary"
                style={{ width: '100%', padding: '10px' }}
                disabled={!allSafetyChecked}
                onClick={() => setStep('CONNECT')}
              >
                Continue to Connection
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Connection picker */}
        {step === 'CONNECT' && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
              <Settings className="text-purple" size={28} />
              <h2 className="modal-title" style={{ margin: 0 }}>Connect Device</h2>
            </div>
            
            <p className="modal-body">
              Select the serial port corresponding to your linear motor interface to begin calibration.
            </p>

            <div className="input-group" style={{ margin: '20px 0' }}>
              <label className="input-label" htmlFor="port-picker">Serial COM/TTY Port</label>
              {isLoadingPorts ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Scanning available ports...</div>
              ) : (
                <>
                  <select
                    id="port-picker"
                    className="select-widget"
                    style={{ width: '100%', padding: '10px' }}
                    value={selectedPort}
                    onChange={(e) => setSelectedPort(e.target.value)}
                  >
                    {ports.map((p) => (
                      <option key={p.device} value={p.device}>
                        {p.description} ({p.device})
                      </option>
                    ))}
                    <option value="mock">Virtual Simulation Motor (mock)</option>
                  </select>
                  {ports.length === 0 && (
                    <div style={{ marginTop: '10px', padding: '10px', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: '6px', fontSize: '0.85rem', color: 'var(--color-warning)' }}>
                      ⚠️ No physical devices detected. Defaulting to Offline Simulation Mode using the virtual motor.
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="modal-buttons" style={{ display: 'flex', gap: '10px' }}>
              <button className="btn btn-secondary" onClick={() => setStep('WELCOME')}>
                Back
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                disabled={isLoadingPorts}
                onClick={handleStartCalibration}
              >
                Connect &amp; Calibrate
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Calibration In Progress */}
        {step === 'CALIBRATING' && (
          <div style={{ textAlign: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '15px' }}>
              <Activity className="text-warning animate-pulse" size={48} />
            </div>
            
            <h2 className="modal-title" style={{ color: 'var(--color-warning)' }}>Calibrating Actuator...</h2>
            
            <div className="banner banner-warning" style={{ margin: '15px 0', border: '1px solid rgba(245,158,11,0.3)', borderRadius: '6px' }}>
              ⚠️ DANGER: Keep hands clear! The shaft is moving to detect endpoints.
            </div>

            <p className="modal-body" style={{ minHeight: '48px', fontSize: '0.95rem' }}>
              {getCalibStatusText()}
            </p>

            {/* Live Progress Bar */}
            <div style={{ width: '100%', height: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '5px', overflow: 'hidden', margin: '20px 0' }}>
              <div 
                style={{ 
                  width: `${getCalibProgressPercent()}%`, 
                  height: '100%', 
                  background: 'linear-gradient(90deg, var(--color-warning) 0%, var(--color-warning-bg) 100%)',
                  transition: 'width 0.4s ease'
                }} 
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              <span>Step progress: {getCalibProgressPercent()}%</span>
              <span>Position: {Math.round(telemetry.position_um / 1000)} mm</span>
            </div>
          </div>
        )}

        {/* Step 4: Complete */}
        {step === 'COMPLETE' && (
          <div style={{ textAlign: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '15px' }}>
              <CheckCircle className="text-success" size={48} />
            </div>

            <h2 className="modal-title" style={{ color: 'var(--color-success)' }}>Calibration Successful</h2>
            
            <p className="modal-body" style={{ margin: '15px 0 25px 0' }}>
              Physical boundaries successfully mapped.
              <br /><br />
              <strong style={{ color: 'var(--text-bright)', fontSize: '1.1rem' }}>
                Safe Stroke Range: {(telemetry.calibrated_length_um / 1000).toFixed(0)} mm
              </strong>
            </p>

            <button
              className="btn btn-primary"
              style={{ width: '100%', padding: '12px', fontSize: '1rem' }}
              onClick={onClose}
            >
              Enter Dashboard
            </button>
          </div>
        )}

      </div>
    </div>
  );
});
