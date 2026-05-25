/**
 * Calibration startup dialog — shown on every launch.
 * Calibration is mandatory; there is no skip option.
 */
export function StartupModal({ onCalibrate }) {
  return (
    <div className="modal-overlay">
      <div className="modal-dialog">
        <h2 className="modal-title">Calibration Required</h2>
        <p className="modal-body">
          Wavedriver must calibrate the physical stroke range of the Orca 6 motor
          before any pattern can run.
          <br /><br />
          The shaft will move slowly to both end-stops to measure the safe travel
          distance. Ensure the path is completely clear before proceeding.
        </p>
        <div className="modal-buttons">
          <button className="btn btn-primary" onClick={onCalibrate}>
            Begin Calibration
          </button>
        </div>
      </div>
    </div>
  );
}
