"""Structural Protocols for the Orca actuator SDK boundary.

``mock_actuator.Actuator`` and ``pyorcasdk.Actuator`` both satisfy ``ActuatorProtocol``.
Annotating controller internals against these Protocols lets mypy check the control
code without requiring a typed ``pyorcasdk`` stub.
"""

from typing import Any, Protocol


class OrcaErrorProtocol(Protocol):
    """Minimal interface for OrcaError objects returned by SDK calls."""

    def __bool__(self) -> bool: ...

    def what(self) -> str: ...


class StreamDataProtocol(Protocol):
    """Fields on the stream-data object returned by ``actuator.get_stream_data()``."""

    position: int
    force: int
    power: int
    temperature: int
    voltage: int
    errors: int


class ActuatorProtocol(Protocol):
    """Structural interface satisfied by both ``mock_actuator.Actuator`` and ``pyorcasdk.Actuator``.

    Only methods called by MotorController are listed; the real SDK may expose more.
    """

    def open_serial_port(
        self, port_path: str, baud_rate: int = ..., interframe_delay: int = ...
    ) -> OrcaErrorProtocol: ...

    def close_serial_port(self) -> None: ...

    def enable_stream(self) -> None: ...

    def disable_stream(self) -> None: ...

    def set_mode(self, motor_mode: Any) -> Any: ...

    def set_max_force(self, max_force: int) -> Any: ...

    def tune_position_controller(
        self, pgain: int, igain: int, dvgain: int, sat: int, dgain: int = ...
    ) -> None: ...

    def set_streamed_force_mN(self, force: int) -> None: ...

    def set_streamed_position_um(self, position: int) -> None: ...

    def run(self) -> None: ...

    def get_stream_data(self) -> StreamDataProtocol: ...

    def write_register_blocking(
        self, reg_address: int, write_data: int, priority: Any = ...
    ) -> Any: ...

    def time_since_last_response_microseconds(self) -> int: ...

    def zero_position(self) -> Any: ...

    def clear_errors(self) -> Any: ...
