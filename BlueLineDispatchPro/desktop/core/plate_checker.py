"""
BlueLineDispatchPro — LSPDFR Plate Checker Bridge

Writes a plate query to a shared folder that the in-game C# plugin watches.
The plugin looks up the plate via LSPDFR API and writes the real result back.
Python reads the result and passes it to GPT for formatting.
"""
import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

# ── Phonetic alphabet decoder ─────────────────────────────────────────────────
PHONETIC = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D",
    "echo": "E", "foxtrot": "F", "golf": "G", "hotel": "H",
    "india": "I", "juliet": "J", "kilo": "K", "lima": "L",
    "mike": "M", "november": "N", "oscar": "O", "papa": "P",
    "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T",
    "uniform": "U", "victor": "V", "whiskey": "W", "x-ray": "X",
    "yankee": "Y", "zulu": "Z",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "niner": "9",
}

# Words that look like plates but aren't
_STOPWORDS = {
    "SHOW", "CODE", "COPY", "ROGER", "DISP", "UNIT", "STOP",
    "PLATE", "CHECK", "STANDBY", "GIVE", "WITH", "THAT", "THIS",
    "FROM", "HAVE", "BEEN", "WILL", "YOUR", "CLEAR", "ADAM",
}

# Phrases that indicate the user wants a plate run
_PLATE_TRIGGERS = [
    "run a plate", "run the plate", "run plate", "plate check",
    "check a plate", "check the plate", "run that plate",
    "run this plate", "plate run", "check for wants",
]


def is_plate_request(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in _PLATE_TRIGGERS)


def extract_plate(text: str) -> str | None:
    """
    Extract a license plate from a radio transmission.
    Handles direct plates ("645TAR") and phonetic ("6-4-5 Tango-Alpha-Romeo").
    """
    t = text.lower()
    # Decode phonetic alphabet (longest first to avoid partial matches)
    for word, char in sorted(PHONETIC.items(), key=lambda x: -len(x[0])):
        t = re.sub(rf'\b{re.escape(word)}\b', char, t)
    # Find plate-shaped strings (3–8 alphanumeric chars)
    candidates = re.findall(r'[A-Z0-9]{3,8}', t.upper())
    candidates = [c for c in candidates if c not in _STOPWORDS]
    return candidates[0] if candidates else None


class PlateChecker:
    """File-bridge between Python dispatcher and the LSPDFR C# plugin."""

    def __init__(self, bridge_path: str, timeout: float = 6.0):
        self.bridge_path   = bridge_path
        self.timeout       = timeout
        self._query_file   = os.path.join(bridge_path, "plate_query.txt")
        self._response_file = os.path.join(bridge_path, "plate_response.json")

    def is_available(self) -> bool:
        """True if the bridge folder exists (plugin has created it)."""
        return os.path.isdir(self.bridge_path)

    def query(self, plate: str) -> dict | None:
        """
        Send plate to LSPDFR plugin and wait for the real result.
        Returns a dict with vehicle/owner data, or None on timeout.
        """
        try:
            os.makedirs(self.bridge_path, exist_ok=True)
            # Clear stale response
            if os.path.exists(self._response_file):
                os.remove(self._response_file)
            # Write the query
            with open(self._query_file, "w") as f:
                f.write(plate.strip().upper())
            logger.info(f"[PLATE] Query sent: {plate}")
            # Wait for plugin to respond
            start = time.time()
            while time.time() - start < self.timeout:
                if os.path.exists(self._response_file):
                    with open(self._response_file, "r") as f:
                        data = json.load(f)
                    logger.info(f"[PLATE] Response: {data}")
                    return data
                time.sleep(0.2)
            logger.warning(f"[PLATE] Timeout waiting for response on {plate}")
            return None
        except Exception as e:
            logger.error(f"[PLATE] Bridge error: {e}")
            return None

    def format_for_gpt(self, data: dict, plate: str) -> str:
        """
        Convert raw LSPDFR plate data into a GPT context injection string.
        GPT will use this to generate a realistic radio response.
        """
        if not data or not data.get("found"):
            return (
                f"REAL PLATE DATA: Plate {plate} — no vehicle found in the area with that plate. "
                f"Tell the officer the plate comes back with no record locally, "
                f"advise them to verify."
            )
        flags = []
        if data.get("stolen"):
            flags.append("VEHICLE REPORTED STOLEN")
        if data.get("wanted"):
            flags.append(f"OWNER {data.get('owner','UNKNOWN')} HAS ACTIVE WARRANT")
        if not data.get("license_valid", True):
            flags.append("OWNER LICENSE SUSPENDED OR REVOKED")
        if not flags:
            flags.append("No wants or warrants")

        return (
            f"REAL PLATE DATA from LSPDFR (use this exactly, do not invent data):\n"
            f"Plate: {data.get('plate', plate)}\n"
            f"Vehicle: {data.get('color','Unknown')} {data.get('model','Unknown')}\n"
            f"Owner: {data.get('owner','Unknown')}\n"
            f"DOB: {data.get('dob','Unknown')}\n"
            f"Registration: {data.get('registration','Valid')}\n"
            f"Flags: {', '.join(flags)}\n"
            f"Generate a professional dispatcher radio response using ONLY the above data."
        )
