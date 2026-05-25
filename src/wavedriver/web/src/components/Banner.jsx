import { ShieldAlert, AlertTriangle, Thermometer } from 'lucide-react';

/**
 * Global status banners shown above the header.
 * Priority: ESTOP > ERROR > temp warning (all mutually exclusive in practice).
 */
export function Banner({ telemetry }) {
  if (telemetry.state_enum === "ESTOP") {
    return (
      <div className="banner banner-estop">
        <ShieldAlert size={20} />
        EMERGENCY STOP — {telemetry.error_msg || "Safety Limit Exceeded"}
      </div>
    );
  }

  if (telemetry.state_enum === "ERROR") {
    return (
      <div className="banner banner-error">
        <AlertTriangle size={20} />
        DEVICE ERROR: {telemetry.error_msg}
      </div>
    );
  }

  if (telemetry.temp_warning) {
    return (
      <div className="banner banner-warning">
        <Thermometer size={18} />
        Temperature Warning: {telemetry.temperature_C} °C — reduce intensity to cool down
      </div>
    );
  }

  return null;
}
