"""
BlueLineDispatchPro — CAD Engine
Thread-safe data model for all CAD data with event callbacks.
"""
import threading
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())[:8].upper()


class CADEngine:
    """Central data store for all CAD/MDT state. Thread-safe."""

    def __init__(self, settings: Optional[Dict] = None):
        self._lock = threading.RLock()
        self.settings = settings or {}
        self._callbacks: Dict[str, List[Callable]] = {}

        # Core data stores
        self.active_calls: List[Dict] = []
        self.units: List[Dict] = []
        self.bolos: List[Dict] = []
        self.dispatch_log: List[Dict] = []
        self.plate_data: Optional[Dict] = None
        self.ped_data: Optional[Dict] = None

        # Connection state
        self.companion_connected: bool = False
        self.companion_last_seen: Optional[str] = None
        self.listener_active: bool = False
        self.scanner_active: bool = False
        self.audio_muted: bool = False

    # ── Event System ──────────────────────────────────────────────────────────

    def on(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        self._callbacks.setdefault(event, []).append(callback)

    def emit(self, event: str, data: Any = None) -> None:
        """Fire all callbacks registered for event."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(data)
            except Exception as e:
                logger.error(f"Callback error for event '{event}': {e}")

    # ── Calls ─────────────────────────────────────────────────────────────────

    def add_call(self, call_data: Dict) -> Dict:
        with self._lock:
            call = {
                "call_id": call_data.get("call_id", _new_id()),
                "timestamp": call_data.get("timestamp", _now_iso()),
                "type": call_data.get("type", "Unknown"),
                "code": call_data.get("code", ""),
                "priority": int(call_data.get("priority", 3)),
                "status": call_data.get("status", "pending"),
                "location": call_data.get("location", "Unknown Location"),
                "coords": call_data.get("coords", {"x": 0, "y": 0, "z": 0}),
                "description": call_data.get("description", ""),
                "caller": call_data.get("caller", "Anonymous"),
                "assigned_units": call_data.get("assigned_units", []),
                "notes": call_data.get("notes", ""),
                "source": call_data.get("source", "manual"),
            }
            self.active_calls.insert(0, call)
            self._log(f"[CALL] New call #{call['call_id']}: {call['type']} at {call['location']}", "call")
            self.emit("calls_updated", self.active_calls)
            return call

    def update_call(self, call_id: str, updates: Dict) -> bool:
        with self._lock:
            for call in self.active_calls:
                if call["call_id"] == call_id:
                    call.update(updates)
                    self._log(f"[CALL] Updated call #{call_id}: {updates.get('status', '')}", "update")
                    self.emit("calls_updated", self.active_calls)
                    return True
        return False

    def close_call(self, call_id: str) -> bool:
        with self._lock:
            for call in self.active_calls:
                if call["call_id"] == call_id:
                    call["status"] = "closed"
                    self._log(f"[CALL] Closed call #{call_id}", "close")
                    self.emit("calls_updated", self.active_calls)
                    return True
        return False

    def get_active_calls(self) -> List[Dict]:
        with self._lock:
            return [c for c in self.active_calls if c.get("status") != "closed"]

    # ── Units ─────────────────────────────────────────────────────────────────

    def upsert_unit(self, unit_data: Dict) -> Dict:
        with self._lock:
            uid = unit_data.get("unit_id", "")
            for i, u in enumerate(self.units):
                if u["unit_id"] == uid:
                    self.units[i].update(unit_data)
                    self.units[i]["last_update"] = _now_iso()
                    self.emit("units_updated", self.units)
                    return self.units[i]
            unit = {
                "unit_id": uid or _new_id(),
                "name": unit_data.get("name", "Unknown"),
                "badge": unit_data.get("badge", ""),
                "rank": unit_data.get("rank", "Officer"),
                "department": unit_data.get("department", "LSPD"),
                "status": unit_data.get("status", "available"),
                "status_code": unit_data.get("status_code", "10-8"),
                "location": unit_data.get("location", ""),
                "coords": unit_data.get("coords", {"x": 0, "y": 0, "z": 0}),
                "vehicle": unit_data.get("vehicle", ""),
                "call_assigned": unit_data.get("call_assigned", None),
                "last_update": _now_iso(),
            }
            self.units.append(unit)
            self.emit("units_updated", self.units)
            return unit

    # ── Plate / Ped Data ──────────────────────────────────────────────────────

    def set_plate_data(self, data: Dict) -> None:
        with self._lock:
            self.plate_data = data
            plate = data.get("plate", "???")
            owner = data.get("owner", {})
            name = f"{owner.get('first_name','')} {owner.get('last_name','')}".strip()
            stolen = "⚠ STOLEN" if data.get("stolen") else ""
            warrants = "⚠ WARRANTS" if owner.get("warrants") else ""
            flags = " ".join(filter(None, [stolen, warrants]))
            self._log(f"[PLATE] {plate} — {name} {flags}", "plate")
            self.emit("plate_updated", data)

    def set_ped_data(self, data: Dict) -> None:
        with self._lock:
            self.ped_data = data
            name = f"{data.get('first_name','')} {data.get('last_name','')}".strip()
            warrants = "⚠ WARRANTS" if data.get("warrants") else ""
            self._log(f"[PED] {name} {warrants}", "ped")
            self.emit("ped_updated", data)

    # ── BOLOs ─────────────────────────────────────────────────────────────────

    def add_bolo(self, bolo_data: Dict) -> Dict:
        with self._lock:
            bolo = {
                "bolo_id": bolo_data.get("bolo_id", _new_id()),
                "timestamp": bolo_data.get("timestamp", _now_iso()),
                "type": bolo_data.get("type", "person"),
                "priority": int(bolo_data.get("priority", 2)),
                "subject": bolo_data.get("subject", ""),
                "description": bolo_data.get("description", ""),
                "reason": bolo_data.get("reason", ""),
                "plate": bolo_data.get("plate", ""),
                "active": True,
                "issued_by": bolo_data.get("issued_by", "Dispatch"),
            }
            self.bolos.insert(0, bolo)
            self._log(f"[BOLO] {bolo['type'].upper()}: {bolo['subject']}", "bolo")
            self.emit("bolos_updated", self.bolos)
            return bolo

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, message: str, category: str = "general") -> None:
        entry = {"timestamp": _now_iso(), "message": message, "category": category}
        max_entries = self.settings.get("cad", {}).get("max_log_entries", 500)
        self.dispatch_log.insert(0, entry)
        if len(self.dispatch_log) > max_entries:
            self.dispatch_log = self.dispatch_log[:max_entries]
        self.emit("log_updated", entry)
        logger.info(message)

    def log(self, message: str, category: str = "general") -> None:
        with self._lock:
            self._log(message, category)

    # ── Panic ─────────────────────────────────────────────────────────────────

    def trigger_panic(self, unit_id: Optional[str] = None) -> None:
        with self._lock:
            uid = unit_id or self.settings.get("cad", {}).get("unit_id", "UNKNOWN")
            self._log(f"🚨 PANIC BUTTON ACTIVATED — Unit {uid} — ALL UNITS RESPOND", "panic")
            self.emit("panic", {"unit_id": uid, "timestamp": _now_iso()})

    # ── Companion Status ──────────────────────────────────────────────────────

    def set_companion_connected(self, connected: bool) -> None:
        with self._lock:
            prev = self.companion_connected
            self.companion_connected = connected
            if connected:
                self.companion_last_seen = _now_iso()
            if prev != connected:
                status = "Connected" if connected else "Disconnected"
                self._log(f"[COMPANION] {status}", "system")
                self.emit("companion_status", connected)
