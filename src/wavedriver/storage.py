"""Persistence layer for Wavedriver user data.

All writes are atomic (temp file + os.replace).  Corrupt files are renamed to
``.bak`` and logged rather than silently ignored so the user can recover data.
"""

import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger("wavedriver.storage")

_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "wavedriver"

SCHEMA_VERSION = 1
_HISTORY_MAX_ENTRIES = 500


class SessionData(TypedDict):
    """Safety settings persisted across runs.

    Only ``safety_force_n``, ``max_session_s``, and ``history_enabled`` are stored —
    motion parameters reset to defaults each session so calibration is always required.
    """

    safety_force_n: float
    max_session_s: int
    history_enabled: bool


class Storage:
    """Reads and writes the three persistent stores: presets, session settings, and history.

    Args:
        config_dir: Override the default ``~/.config/wavedriver`` directory.  Used in
            tests to isolate writes from the user's real config.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or _DEFAULT_CONFIG_DIR

    # ── File paths ────────────────────────────────────────────────────────────

    @property
    def presets_file(self) -> Path:
        return self._dir / "presets.json"

    @property
    def session_file(self) -> Path:
        return self._dir / "session.json"

    @property
    def history_file(self) -> Path:
        return self._dir / "history.jsonl"

    # ── Low-level I/O ─────────────────────────────────────────────────────────

    def _atomic_write(self, path: Path, data: str) -> None:
        """Write *data* to *path* atomically using a sibling temp file + os.replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """Parse *path* as JSON.

        Returns ``None`` if the file is missing.  On parse failure, renames the bad
        file to ``.bak``, logs a warning, and returns ``None`` so callers fall back
        to defaults rather than crashing.
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
            return None

        try:
            result: dict[str, Any] = json.loads(raw)
            return result
        except json.JSONDecodeError:
            bak = path.with_suffix(path.suffix + ".bak")
            try:
                path.rename(bak)
                logger.warning("Corrupt JSON at %s — backed up to %s, using defaults", path, bak)
            except OSError as exc:
                logger.warning("Could not back up corrupt %s: %s", path, exc)
            return None

    # ── Presets ───────────────────────────────────────────────────────────────

    def load_presets(self) -> dict[str, Any]:
        """Return saved preset slots, or ``{}`` if none exist."""
        data = self._read_json(self.presets_file)
        return data if data is not None else {}

    def save_presets(self, presets_data: dict[str, Any]) -> None:
        """Atomically overwrite the presets file."""
        self._atomic_write(self.presets_file, json.dumps(presets_data))

    # ── Session settings ──────────────────────────────────────────────────────

    def load_session(self, default_safety_n: float) -> SessionData:
        """Return persisted safety settings, clamped to valid ranges.

        Only ``safety_force_n`` and ``max_session_s`` are restored — motion parameters
        reset to defaults each session so calibration is always required.
        """
        data = self._read_json(self.session_file)
        if data is None:
            return SessionData(
                safety_force_n=default_safety_n, max_session_s=0, history_enabled=True
            )
        return SessionData(
            safety_force_n=max(5.0, min(60.0, float(data.get("safety_force_n", default_safety_n)))),
            max_session_s=max(0, min(7200, int(data.get("max_session_s", 0)))),
            history_enabled=bool(data.get("history_enabled", True)),
        )

    def save_session(self, session_data: dict[str, Any], default_safety_n: float) -> None:
        """Atomically overwrite the session settings file."""
        to_save = {
            "schema_version": SCHEMA_VERSION,
            "safety_force_n": session_data.get("safety_force_n", default_safety_n),
            "max_session_s": session_data.get("max_session_s", 0),
            "history_enabled": session_data.get("history_enabled", True),
        }
        self._atomic_write(self.session_file, json.dumps(to_save))

    # ── Session history ───────────────────────────────────────────────────────

    def append_history(self, record: dict[str, Any]) -> None:
        """Append one session record to the JSONL history log with an ISO timestamp."""
        entry = dict(record)
        entry["timestamp"] = datetime.datetime.now().isoformat()
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        self._prune_history()

    def _prune_history(self) -> None:
        """Trim the history file to at most _HISTORY_MAX_ENTRIES lines."""
        try:
            lines = [
                ln
                for ln in self.history_file.read_text(encoding="utf-8").strip().splitlines()
                if ln
            ]
            if len(lines) <= _HISTORY_MAX_ENTRIES:
                return
            self._atomic_write(self.history_file, "\n".join(lines[-_HISTORY_MAX_ENTRIES:]) + "\n")
        except OSError:
            pass

    def clear_history(self) -> None:
        """Delete all session history records."""
        try:
            self.history_file.unlink(missing_ok=True)
        except OSError:
            pass

    def load_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent *limit* session records, newest first.

        Malformed lines are skipped silently; they do not prevent valid records from loading.
        """
        try:
            if not self.history_file.exists():
                return []
            lines = [
                line
                for line in self.history_file.read_text(encoding="utf-8").strip().splitlines()
                if line
            ]
            records: list[dict[str, Any]] = []
            for line in lines[-limit:]:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return list(reversed(records))
        except OSError:
            return []
