"""
BlueLineDispatchPro — LSPDFR Plate Checker Bridge

Primary:  Writes a plate query to a shared folder that the in-game C# plugin
          watches. The plugin looks up the plate via LSPDFR API and writes the
          real result back.
Fallback: If the plugin is not running, generates realistic procedural data
          seeded by the plate string so the same plate always returns the same
          owner / vehicle / flags.
"""
import hashlib
import json
import logging
import os
import random
import re
import time

logger = logging.getLogger(__name__)

# ── Procedural data pools (seeded by plate for consistency) ───────────────────
_MALE_FIRST   = ["James","Michael","Robert","David","John","Carlos","Miguel",
                 "Andre","Tyrone","Kevin","Brian","Darnell","Marcus","Antonio",
                 "DeShawn","Trevor","Brandon","Tyler","Justin","Nathan","Eric"]
_FEMALE_FIRST = ["Maria","Jennifer","Linda","Patricia","Sarah","Ashley",
                 "Brittany","Heather","Jessica","Emily","Vanessa","Tanya",
                 "Latoya","Nicole","Amanda","Crystal","Diana","Monique"]
_LAST  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
          "Rodriguez","Martinez","Anderson","Taylor","Thomas","Jackson","White",
          "Harris","Clark","Lewis","Robinson","Walker","Hall","Allen","Young",
          "Hernandez","King","Scott","Green","Adams","Baker","Nelson","Carter"]
_MONTHS = [1,2,3,4,5,6,7,8,9,10,11,12]

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

# Phrases that indicate the user wants a person / driver ID check
_ID_TRIGGERS = [
    "run his id", "run her id", "run their id", "run the driver",
    "run a 28", "run 28", "28 on the driver", "28 on him", "28 on her",
    "check his id", "check her id", "run his information",
    "run her information", "run the subject", "id on the driver",
    "run that subject", "run the occupant",
]


def is_plate_request(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in _PLATE_TRIGGERS)


def is_id_request(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in _ID_TRIGGERS)


def extract_plate(text: str) -> str | None:
    """
    Extract a license plate from a radio transmission.
    Handles:
      - Direct plates:       "64AZG074"
      - Phonetic words:      "6-4 Alpha Zulu Golf 0-7-4"
      - Spelled out chars:   "6 4 A Z G 0 7 4"  (each char space-separated)
    """
    t = text.lower()

    # 1. Decode phonetic alphabet (longest word first to avoid partial matches)
    for word, char in sorted(PHONETIC.items(), key=lambda x: -len(x[0])):
        t = re.sub(rf'\b{re.escape(word)}\b', char, t)

    # 2. Join sequences of individual space-separated alphanumeric chars
    #    e.g. "6 4 a z g 0 7 4" → "64azg074"
    #    Repeat until stable so long chains collapse fully
    for _ in range(10):
        new_t = re.sub(r'\b([a-z0-9]) ([a-z0-9])\b', r'\1\2', t)
        if new_t == t:
            break
        t = new_t

    upper = t.upper()
    candidates = re.findall(r'[A-Z0-9]{3,8}', upper)
    candidates = [c for c in candidates if c not in _STOPWORDS]

    if not candidates:
        return None

    # 3. Prefer candidates that look like actual plates:
    #    contain BOTH letters and digits (e.g. "64AZG074" beats "GOT")
    mixed = [c for c in candidates if re.search(r'[A-Z]', c) and re.search(r'[0-9]', c)]
    if mixed:
        return max(mixed, key=len)

    # 4. Fall back to longest remaining candidate
    return max(candidates, key=len)


class PlateChecker:
    """
    Plate lookup with two modes:
    1. Real data  — file-bridge to in-game C# plugin (when running).
    2. Procedural — seeded by plate string, consistent across lookups.
    Always returns data; never blocks indefinitely.
    """

    def __init__(self, bridge_path: str, timeout: float = 6.0):
        self.bridge_path    = bridge_path
        self.timeout        = timeout
        self._query_file    = os.path.join(bridge_path, "plate_query.txt")
        self._response_file = os.path.join(bridge_path, "plate_response.json")

    def is_available(self) -> bool:
        """Always True — procedural fallback means we always have an answer."""
        return True

    def _plugin_running(self) -> bool:
        """Check if the C# bridge folder was created by the in-game plugin."""
        return os.path.isdir(self.bridge_path)

    def _procedural_query(self, plate: str) -> dict:
        """Generate consistent plate data seeded by plate — same plate = same person always."""
        seed = int(hashlib.md5(plate.upper().encode()).hexdigest(), 16)
        rng  = random.Random(seed)

        # Gender is fixed for this plate — 70% male, 30% female
        is_male = rng.random() < 0.70
        first  = rng.choice(_MALE_FIRST if is_male else _FEMALE_FIRST)
        last   = rng.choice(_LAST)
        month  = rng.choice(_MONTHS)
        day    = rng.randint(1, 28)
        year   = rng.randint(1960, 2000)
        wanted    = rng.random() < 0.08   # 8% chance active warrant
        suspended = rng.random() < 0.07   # 7% chance suspended license
        expired   = rng.random() < 0.06   # 6% chance expired registration

        return {
            "found":         True,
            "plate":         plate.upper(),
            "owner":         first + " " + last,
            "dob":           "%02d/%02d/%d" % (month, day, year),
            "wanted":        wanted,
            "license_valid": not suspended,
            "registration":  "Expired" if expired else "Valid",
            "stolen":        False,
            "source":        "procedural",
        }

    def query(self, plate: str) -> dict:
        """
        Try the C# plugin bridge first; fall back to procedural if not running.
        When the bridge returns source='shvdn' it has real vehicle data but
        the LSPDFR persona reflection didn't fire, so we merge in a procedural
        persona seeded by the plate so the owner stays consistent.
        """
        plate = plate.strip().upper()

        # ── Try real plugin bridge ────────────────────────────────────────────
        if os.path.isdir(self.bridge_path):
            try:
                if os.path.exists(self._response_file):
                    os.remove(self._response_file)
                with open(self._query_file, "w") as f:
                    f.write(plate)
                logger.info("[PLATE] Query sent to plugin: " + plate)
                start = time.time()
                while time.time() - start < self.timeout:
                    if os.path.exists(self._response_file):
                        with open(self._response_file, "r") as f:
                            data = json.load(f)
                        logger.info("[PLATE] Plugin response: " + str(data))
                        # Real vehicle data but no LSPDFR persona — merge procedural
                        if data.get("source") == "shvdn" and not data.get("owner"):
                            proc = self._procedural_query(plate)
                            data["owner"]         = proc["owner"]
                            data["dob"]           = proc["dob"]
                            data["wanted"]        = proc["wanted"]
                            data["license_valid"] = proc["license_valid"]
                            data["registration"]  = proc["registration"]
                            data["source"]        = "shvdn+procedural"
                        return data
                    time.sleep(0.2)
                logger.warning("[PLATE] Plugin timeout — using procedural")
            except Exception as e:
                logger.error("[PLATE] Bridge error: " + str(e))

        # ── Procedural fallback ───────────────────────────────────────────────
        data = self._procedural_query(plate)
        logger.info("[PLATE] Procedural result for " + plate + ": " + str(data))
        return data

    def format_for_gpt(self, data: dict, plate: str) -> str:
        """Convert plate data into a GPT context string for radio response."""
        if not data or not data.get("found"):
            return (
                "PLATE DATA: Plate " + plate + " — no record on file. "
                "Tell the officer the plate comes back no record, advise to verify."
            )

        flags = []
        if data.get("stolen"):
            flags.append("VEHICLE REPORTED STOLEN — advise officer, use caution")
        if data.get("wanted"):
            flags.append("OWNER HAS ACTIVE WARRANT — advise officer")
        if not data.get("license_valid", True):
            flags.append("DRIVER LICENSE SUSPENDED OR REVOKED")
        if data.get("registration") == "Expired":
            flags.append("REGISTRATION EXPIRED")
        if not flags:
            flags.append("No wants or warrants, valid registration")

        # Include vehicle description when bridge gave us real game data
        vehicle_line = ""
        src = data.get("source", "procedural")
        if src in ("lspdfr", "shvdn", "shvdn+procedural") and data.get("model"):
            vehicle_line = "\nVehicle: " + data.get("color","") + " " + data.get("model","")

        return (
            "PLATE RESULT — check is COMPLETE, do NOT say 'stand by' again.\n"
            "Read back ALL of the following over radio like a real dispatcher:\n"
            "Plate: " + data.get("plate", plate) + vehicle_line + "\n"
            "Registered to: " + data.get("owner", "Unknown") + "\n"
            "DOB: " + data.get("dob", "Unknown") + "\n"
            "Registration: " + data.get("registration", "Valid") + "\n"
            "Status: " + ", ".join(flags) + "\n"
            "End with 'Anything further, [callsign]?'"
        )
