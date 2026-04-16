"""
BlueLineDispatchPro — Dispatcher Audio Generator
Generates dispatcher audio using Windows SAPI via PowerShell.
100% offline — no internet, no API keys, no rate limits, no freeze issues.

Usage:
    python generate_audio.py
    python generate_audio.py --voice David
    python generate_audio.py --category plate
    python generate_audio.py --list-voices
"""
import argparse
import subprocess
from pathlib import Path

# ── All dispatcher phrases by category ───────────────────────────────────────
# Each entry is one WAV file. Edit freely — add as many as you want.

PHRASES = {
    "acknowledgment": [
        "10-4, copy that.",
        "Dispatch copies.",
        "Received. 10-4.",
        "Copy, go ahead.",
        "10-4, understood.",
        "Dispatch copies that. Stand by.",
        "Copy that, all units.",
        "10-4. Dispatch out.",
        "Received, copy.",
        "Affirmative. Dispatch copies.",
        "10-4. Noted.",
        "Copy. Units are advised.",
        "Dispatch acknowledges. 10-4.",
        "Copy that transmission.",
        "10-4, disregard. Cancel that call.",
        "Dispatch copies the cancellation.",
        "10-22, disregard.",
        "Copy, 10-22. Disregard all units.",
        "Code 4, all units. Situation is clear.",
        "10-4. Code 4 on that.",
        "Copy your 10-24. Assignment complete.",
        "10-4. You are clear to 10-8.",
        "Copy, you are 10-8 and available.",
        "Dispatch copies. Have a safe shift.",
        "10-4. All units copy.",
    ],
    "backup": [
        "Copy, backup is en route to your location.",
        "All units, backup is requested at your location. Please respond immediately.",
        "10-4. Available units, please respond for backup.",
        "Copy that. Units are being dispatched to your location now.",
        "All available units, backup is requested. Nearest unit respond.",
        "10-4. Backup is on the way. ETA two minutes.",
        "Copy your 10-33. All units respond immediately.",
        "Dispatching backup to your 20 now. Stand by.",
        "10-4. Two units are en route to your location.",
        "All units — officer requesting backup. Code 3 response authorized.",
        "Copy, I have a unit responding to your location.",
        "10-4. Keep your radio open. Backup is two minutes out.",
        "All units copy — backup requested at your location. Respond code 3.",
        "Dispatch to all units. 10-33 active. All available units respond.",
        "Copy that. Air support has been notified.",
        "10-4. SWAT has been advised and is standing by.",
        "Copy. Sergeant is en route to your location.",
        "All units, be advised — backup request is active. Nearest unit please respond.",
    ],
    "callout": [
        "All units, we have a report of a robbery in progress. Nearest unit respond.",
        "Dispatch to all units — 10-90 at the reported location. Units respond code 3.",
        "Copy, units are being dispatched.",
        "10-4. Dispatching available units now.",
        "All units, be advised — we have a disturbance call at your location.",
        "Dispatch to nearest unit — domestic disturbance reported. Please respond.",
        "10-4. Units are responding. ETA is three minutes.",
        "All units, we have a 415 in progress. Available units respond.",
        "Copy that callout. Units are en route.",
        "Dispatch to all units — carjacking reported in your area. Be on lookout.",
        "10-4. Assault with a deadly weapon reported. Units responding code 3.",
        "All units, traffic accident with injuries at the reported location. EMS notified.",
        "Copy. Available units, 10-80 in progress. Please respond.",
        "Dispatch to all units — suspicious persons reported. Nearest unit investigate.",
        "10-4. Burglary in progress. Units responding.",
        "All units — shooting reported. Units respond code 3. EMS en route.",
        "Copy. Units are dispatched. Air support requested.",
        "10-4. All units copy. Respond code 3.",
        "Dispatch to available units — respond to the reported location for investigation.",
        "Copy. Units are on their way.",
    ],
    "chase": [
        "Copy, all units be advised — vehicle pursuit is now active.",
        "10-4. All units, pursuit is in progress. Respond to assist.",
        "Copy pursuit. Air support has been notified and is inbound.",
        "All units, vehicle pursuit is active. Suspect vehicle is described as —",
        "10-4. Pursuit is authorized. Spike strips are being requested.",
        "Copy that. Units are converging on the pursuit route.",
        "All units, foot pursuit is active at the reported location.",
        "10-4. Helicopter is en route to follow the pursuit.",
        "Copy pursuit. All units maintain a safe following distance.",
        "Dispatch to all units — pursuit is crossing into neighboring jurisdiction. Notify county.",
        "10-4. All units, suspect has bailed from the vehicle. Foot pursuit is active.",
        "Copy. Suspect vehicle is approaching your location. Be ready.",
        "All units, pursuit is terminated by the pursuit unit. Stand down.",
        "10-4. Suspect is in custody. Cancel the pursuit.",
        "Copy. Good work, units. Suspect is in custody.",
        "All units, box in maneuver is authorized. Move into position.",
        "10-4. PIT maneuver is authorized at supervisor discretion.",
        "Copy, pursuit unit. All units copy the description.",
    ],
    "general": [
        "All units, be advised — road closure on the main highway.",
        "Dispatch to all units — officer safety bulletin. Stay alert.",
        "All units copy — wanted subject has been spotted in your area.",
        "10-4. All units, shift briefing is at end of watch.",
        "Dispatch to all units — be on the lookout for a stolen vehicle.",
        "All units, the suspect is described as a male, dark clothing, armed.",
        "10-4. All units maintain awareness. High alert status is in effect.",
        "Dispatch to any available unit in the area — report of a suspicious vehicle.",
        "All units, local event is causing traffic delays on the freeway.",
        "Copy. Units, be advised — weather conditions may affect response times.",
        "All units, plainclothes units are operating in your area. Use caution.",
        "10-4. Detective units are en route to the scene.",
        "Dispatch to all units — check your radio for updates on the active call.",
        "All units copy the BOLO. Subject is considered armed and dangerous.",
        "10-4. All units, the sergeant is handling this call. Stand by.",
        "Dispatch to all units — surveillance units are in the area. Do not approach.",
        "All units, be advised — a missing person report is active. Keep an eye out.",
        "10-4. Media is on scene. Units, maintain the perimeter.",
        "All units, shift change is in fifteen minutes. Prepare your reports.",
        "Copy. All units, court subpoenas are available at the front desk.",
        "10-4 all units. Good work today. Stay safe out there.",
        "Dispatch to all units — internal affairs is conducting interviews this week.",
        "All units, the range is available for qualification this weekend.",
        "10-4. Dispatch is monitoring the radio. Units, have a safe patrol.",
        "All units copy. Dispatch clear.",
    ],
    "panic": [
        "ALL UNITS. ALL UNITS. Officer needs assistance immediately! All units respond code 3!",
        "10-99. Officer down. All units respond to the emergency immediately!",
        "EMERGENCY. Shots fired at the officer's location. All units respond NOW!",
        "ALL UNITS CODE 3. Officer needs help immediately. I repeat, all units respond!",
        "10-99. Officer in distress. All available units, respond immediately. Code 3!",
        "All units, officer needs assistance. This is a Code 3 emergency. ALL UNITS RESPOND.",
        "Dispatch to all units — MAYDAY, officer down. Respond immediately. Code 3!",
        "ALL AVAILABLE UNITS. Emergency at the officer's 20. Respond code 3 immediately!",
        "10-99. Officer is in danger. ALL UNITS RESPOND. Air support is being requested.",
        "Emergency broadcast. All units, officer in distress. Drop current assignments and respond.",
        "ALL UNITS CODE 3. I repeat, ALL UNITS CODE 3 to the officer's location. Now!",
        "Officer down. Officer down. All units respond immediately. EMS is being dispatched.",
    ],
    "plate": [
        "Copy, running that plate now. Stand by.",
        "10-4. Checking registration. Stand by one.",
        "Copy, ALPR query has been submitted. Results incoming.",
        "Running that plate. Stand by for results.",
        "10-4. Plate is being checked. Stand by.",
        "Copy. DMV query submitted. Stand by.",
        "Running registration on that plate. Hold for results.",
        "10-4. Checking for warrants and stolen status. Stand by.",
        "Copy that plate. Running now. Stand by.",
        "Dispatch to unit — plate query is submitted. Stand by for return.",
        "10-4. Hold on one — querying that plate now.",
        "Copy. Checking registration, insurance, and wants and warrants. Stand by.",
        "Running that vehicle now. Stand by for the return.",
        "10-4. Plate is in the system. Hold for results.",
        "Copy unit. ALPR hit is being processed. Stand by.",
        "Running that registration. Stand by one.",
        "10-4. Checking stolen vehicle database. Stand by.",
        "Copy. DMV is returning results. Stand by.",
        "Running the plate. Checking for priors and active warrants. Stand by.",
        "10-4. Results incoming. Stand by.",
    ],
    "scene": [
        "10-4. Copy you are on scene.",
        "Copy that. You are noted on scene at your location.",
        "Received. Noted on scene.",
        "10-4. Backup is en route to your location.",
        "Copy. You are on scene. Backup is two minutes out.",
        "10-23 copy. Units noted on scene.",
        "Copy your arrival. Dispatch is standing by.",
        "Received. Noted on scene. Additional units are being dispatched.",
        "10-4. Copy your 10-23. Dispatch copies.",
        "Copy. You are on scene. Air support is overhead.",
        "10-4. You are noted at the location. Keep us advised.",
        "Received. Scene is yours. Keep the radio open.",
        "Copy your on-scene. Dispatch is monitoring.",
        "10-4. Copy arrival. Be advised — suspect may still be on scene.",
        "Received. Noted on scene. EMS is also responding.",
        "Copy that 10-23. Units have arrived. Keep us posted.",
        "10-4. You are on scene. Sergeant is also en route.",
        "Received your arrival. Dispatch copies.",
        "Copy. You are noted on scene. Code 4 when clear.",
        "10-4. Copy on scene. Units are standing by.",
    ],
    "scanner": [
        "Unit 2-Lincoln-15, traffic stop on Strawberry Avenue. Copy.",

        "All units, be advised — road work on the Del Perro Freeway is causing slowdowns.",
        "2-Adam-23, show me 10-8 and available for calls.",
        "Dispatch to all units — 10-4 on that. Units are clear.",
        "14-King-7, I'm 10-6 on a traffic stop at Vinewood Boulevard.",
        "Unit 4-Sam-9, 10-97 to the Rockford Hills call.",
        "Dispatch to 3-Charlie-12 — your 10-28 return is negative. You are clear.",
        "All units, the 415 at Mission Row has been code 4. Units are clearing.",
        "2-Adam-11, handle a 10-54 at the intersection of Forum Drive.",
        "Unit 6-Boy-3, see the man regarding a vehicle dispute on Elgin Avenue.",
        "Dispatch — all units, shots fired call is now code 4. Stand down.",
        "4-King-19, your warrant return is negative. Subject is clear.",
        "All units, warrant subject has been booked and processed at Mission Row.",
        "3-Sam-7, clear from your last call. What is your status?",
        "Dispatch to all units — end of watch briefing at 0200 hours in the briefing room.",
        "Unit 5-Adam-1, respond to the disturbance call on Forum Drive.",
        "2-Lincoln-8, your traffic stop subject has no warrants. You are clear.",
        "All units, be advised — fugitive task force is operating in the Strawberry area.",
        "Dispatch to unit — 10-78, officer needs assistance. All units respond.",
        "4-Boy-14, handle a 10-50 with injuries at the freeway on-ramp.",
        "All units copy. Dispatch is monitoring channel 2 for the operation.",
        "3-Adam-6, show me available. I'm clear from the last call.",
        "Dispatch — 11-99 is now code 4. Good work, units.",
        "All units, the perimeter has been lifted. Units may return to patrol.",
        "2-King-11, your 10-29 return shows the subject has a felony warrant. Use caution.",
        "Unit 7-Sam-3 — 10-4. Stand by for a call assignment.",
        "Dispatch to all units. Shift change in 30 minutes. Final calls are being dispatched.",
        "3-Lincoln-9, are you available for a call in your area?",
        "All units copy. The suspect is in custody at your location. Good work.",
        "Dispatch to all units — have a safe patrol. Dispatch clear.",
    ],
}

# ── PowerShell SAPI generation (reliable, no freeze, no internet) ─────────────

def build_powershell_script(categories: dict, audio_dir: Path, voice_hint: str) -> str:
    """Build a single PowerShell script that generates all WAV files at once."""
    lines = [
        "$ErrorActionPreference = 'Continue'",
        "$tts = New-Object -ComObject SAPI.SpVoice",
        "$tts.Rate = -2",
        "# Select voice",
        "$chosenVoice = $null",
        f"foreach ($v in $tts.GetVoices()) {{",
        f"    if ($v.GetDescription() -like '*{voice_hint}*') {{ $chosenVoice = $v; break }}",
        "}",
        "if ($chosenVoice) { $tts.Voice = $chosenVoice }",
        "Write-Host ('  Voice: ' + $tts.Voice.GetDescription())",
        "",
        "function Write-Wav($text, $path) {",
        "    if ((Test-Path $path) -and ((Get-Item $path).Length -gt 512)) {",
        "        Write-Host \"  skip  $([System.IO.Path]::GetFileName($path))\"",
        "        return",
        "    }",
        "    $stream = New-Object -ComObject SAPI.SpFileStream",
        "    $stream.Open($path, 3, $false)",
        "    $tts.AudioOutputStream = $stream",
        "    $tts.Speak($text)",
        "    $stream.Close()",
        "    Write-Host \"  ok    $([System.IO.Path]::GetFileName($path))\"",
        "}",
        "",
    ]

    for cat, phrases in categories.items():
        cat_dir = audio_dir / cat
        win_dir = str(cat_dir).replace("\\", "\\\\")
        lines.append(f'Write-Host "`n[{cat.upper()}]"')
        lines.append(f'New-Item -ItemType Directory -Force -Path "{win_dir}" | Out-Null')
        for i, phrase in enumerate(phrases, start=1):
            wav_path = cat_dir / f"{i:02d}.wav"
            win_path = str(wav_path).replace("\\", "\\\\")
            # Escape double-quotes inside the phrase for PowerShell
            safe = phrase.replace('"', '`"').replace("'", "\\'")
            lines.append(f'Write-Wav "{safe}" "{win_path}"')
        lines.append("")

    lines.append('Write-Host "`n Done!"')
    return "\n".join(lines)


def run_powershell_script(script: str, script_path: Path) -> bool:
    """Write and execute a PowerShell script file."""
    script_path.write_text(script, encoding="utf-8")
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(script_path),
            ],
            text=True,
        )
        return result.returncode == 0
    finally:
        if script_path.exists():
            script_path.unlink()


def list_voices() -> None:
    """Print available Windows SAPI voices via PowerShell."""
    script = (
        "$tts = New-Object -ComObject SAPI.SpVoice; "
        "foreach ($v in $tts.GetVoices()) { Write-Host $v.GetDescription() }"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate dispatcher audio using Windows SAPI (offline)"
    )
    parser.add_argument(
        "--voice", type=str, default="Zira",
        help="Voice name fragment to search for (default: Zira). Use --list-voices to see all."
    )
    parser.add_argument(
        "--category", type=str, default=None,
        choices=list(PHRASES.keys()),
        help="Generate only one category (default: all)"
    )
    parser.add_argument(
        "--list-voices", action="store_true",
        help="List available Windows TTS voices and exit"
    )
    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return

    base_dir   = Path(__file__).parent
    audio_dir  = base_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    categories = (
        {args.category: PHRASES[args.category]}
        if args.category else PHRASES
    )
    total = sum(len(v) for v in categories.values())

    print(f"\n{'='*60}")
    print(f"  BlueLineDispatchPro — Dispatcher Audio Generator")
    print(f"  Engine: Windows SAPI (offline, no internet, no freeze)")
    print(f"  Voice:  {args.voice}")
    print(f"  Total:  {total} phrases → {audio_dir}")
    print(f"{'='*60}\n")

    script     = build_powershell_script(categories, audio_dir, args.voice)
    ps1_path   = base_dir / "_bldp_generate.ps1"

    print("  Running PowerShell... (this window will show progress)\n")
    ok = run_powershell_script(script, ps1_path)

    # Count generated files
    generated = sum(
        1 for cat in categories
        for f in (audio_dir / cat).glob("*.wav")
        if f.stat().st_size > 512
    )

    print(f"\n{'='*60}")
    if ok:
        print(f"  Done! {generated} WAV files in {audio_dir}")
    else:
        print(f"  Finished with warnings. {generated} files present.")
    print(f"{'='*60}")
    print("\n  Run:  python dispatcher_main.py\n")


if __name__ == "__main__":
    main()

