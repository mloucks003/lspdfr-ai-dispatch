# BlueLineDispatchPro 🚔

> **The most advanced LSPDFR / FiveM police CAD + radio dispatcher tool available.**
> Significantly beyond BlueLine Dispatch v4.0 — real data, real radio effects, full CAD/MDT suite.

---

## What Makes This Different

| Feature | BlueLine v4.0 | **BlueLineDispatchPro** |
|---|---|---|
| Keyword Listening | ✅ Basic | ✅ Advanced + Fuzzy Match |
| Dispatcher Audio | ✅ TTS | ✅ Pre-recorded professional + radio FX |
| CAD / MDT Interface | ❌ None | ✅ Full 7-tab professional CAD |
| Real LSPDFR Data | ❌ Fake/random | ✅ Live from in-game via companion |
| Scanner Mode | ❌ No | ✅ Continuous background chatter |
| Live Map | ❌ No | ✅ Unit + call position overlay |
| Panic Button | ❌ No | ✅ Hotkey + CAD alert |
| BOLO / Warrants | ❌ No | ✅ Full management |
| FiveM Integration | ❌ No | ✅ Companion resource + HTTP API |
| Offline Operation | ✅ | ✅ 100% offline after setup |

---

## Project Structure

```
BlueLineDispatchPro/
├── README.md
├── desktop/                        ← Python desktop app (builds to .exe)
│   ├── main.py                     ← Entry point
│   ├── requirements.txt            ← pip dependencies
│   ├── build.spec                  ← PyInstaller spec
│   ├── config/
│   │   ├── __init__.py             ← Settings loader + APP_DATA_DIR
│   │   ├── settings.json           ← All user-configurable settings
│   │   └── audio_map.json          ← Keyword → audio category mapping
│   ├── core/
│   │   ├── __init__.py
│   │   ├── cad_engine.py           ← CAD data model + event system
│   │   ├── keyword_listener.py     ← Vosk offline speech recognition
│   │   ├── audio_player.py         ← Radio effects + audio playback
│   │   ├── api_server.py           ← Local HTTP API (Flask, port 7623)
│   │   ├── file_watcher.py         ← watchdog JSON file monitor
│   │   ├── scanner_mode.py         ← Background scanner chatter
│   │   └── hotkey_manager.py       ← Global hotkeys (F8/F9/F10/F11)
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── app.py                  ← Main CustomTkinter application
│   │   ├── tabs/
│   │   │   ├── __init__.py
│   │   │   ├── active_calls.py     ← Active calls tab
│   │   │   ├── unit_status.py      ← Unit roster + status
│   │   │   ├── vehicle_lookup.py   ← Plate/vehicle query results
│   │   │   ├── person_lookup.py    ← Ped / person query results
│   │   │   ├── bolos.py            ← BOLOs & warrants
│   │   │   ├── dispatch_log.py     ← Full dispatch log
│   │   │   ├── live_map.py         ← Live unit/call map
│   │   │   └── settings_tab.py     ← Settings panel
│   │   └── components/
│   │       ├── __init__.py
│   │       ├── theme.py            ← Color palette + font constants
│   │       ├── status_bar.py       ← Bottom status bar
│   │       └── tray_icon.py        ← System tray integration
│   ├── audio/
│   │   ├── AUDIO_INSTRUCTIONS.txt  ← How to add your own audio files
│   │   ├── acknowledgment/         ← "10-4", "Copy that", "Received" etc.
│   │   ├── backup/                 ← Backup request responses
│   │   ├── callout/                ← Call dispatched responses
│   │   ├── chase/                  ← Pursuit / vehicle stop responses
│   │   ├── general/                ← General chatter
│   │   ├── panic/                  ← Panic / officer down responses
│   │   ├── plate/                  ← Plate run / ALPR responses
│   │   ├── scene/                  ← On-scene acknowledgments
│   │   └── scanner/                ← Background scanner chatter
│   └── models/
│       └── DOWNLOAD_MODEL.txt      ← Vosk model download instructions
└── companion/                      ← FiveM Lua resource
    ├── fxmanifest.lua
    ├── config.lua
    ├── client/
    │   ├── main.lua                ← Client entry + command hooks
    │   ├── plate_reader.lua        ← ALPR / Wraith ARS integration
    │   ├── callout_hooks.lua       ← LSPDFR/FivePD callout events
    │   └── ped_scanner.lua         ← Ped info capture
    └── server/
        └── main.lua                ← Server-side HTTP relay to desktop API
```

---

## Installation Guide

### Part 1 — Desktop App (Shadow PC)

#### Step 1: Install Python 3.11
Download from https://www.python.org/downloads/  
During install: ✅ Check **"Add Python to PATH"**

#### Step 2: Install Microsoft Visual C++ Build Tools
Required for PyAudio on Windows.  
Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/  
Select: **"Desktop development with C++"**

#### Step 3: Install Dependencies
```batch
cd BlueLineDispatchPro\desktop
pip install -r requirements.txt
```

#### Step 4: Download Vosk Model
Open `desktop/models/DOWNLOAD_MODEL.txt` and follow the instructions.  
Recommended model: `vosk-model-small-en-us-0.15` (~40MB, fast)  
Place the unzipped folder at: `desktop/models/vosk-model-en-us/`

#### Step 5: Add Dispatcher Audio Files
See `desktop/audio/AUDIO_INSTRUCTIONS.txt` for the full guide.  
Place `.wav` files into the category subfolders under `desktop/audio/`.

#### Step 6: Run the App
```batch
python main.py
```
Or build a standalone .exe (see Build section below).

---

### Part 2 — FiveM Companion Resource

#### Step 1: Copy the Companion Folder
Copy the entire `companion/` folder to your FiveM server's `resources/` directory.  
Rename it to `bluedispatch-companion` (or whatever you prefer).

#### Step 2: Add to server.cfg
```
ensure bluedispatch-companion
```

#### Step 3: Configure the Resource
Edit `companion/config.lua`:
- Set `Config.DesktopAPIPort` to match your desktop app (default: `7623`)
- Set `Config.ServerIP` to `127.0.0.1` (same machine) or your server IP
- Enable/disable specific integrations

#### Step 4: Start Your FiveM Server
The companion will auto-connect to the desktop app.  
Check the desktop app's **Dispatch Log** tab — you should see `[COMPANION] Connected`.

---

### Part 3 — Virtual Audio Cable Setup (Optional but Recommended)

For the keyword listener to hear in-game radio/comms:

1. Download **VB-Cable** (free): https://vb-audio.com/Cable/
2. Install and restart your PC
3. In game audio settings, set output to **CABLE Input (VB-Audio)**
4. In BlueLineDispatchPro Settings → Input Device → Select **CABLE Output (VB-Audio)**
5. Your voice + in-game audio will both be analyzed for keywords

---

## Hotkeys

| Key | Action |
|-----|--------|
| **F8** | Toggle keyword listening ON/OFF |
| **F9** | **PANIC BUTTON** — emergency alert + audio |
| **F10** | Toggle scanner mode ON/OFF |
| **F11** | Mute/unmute all audio output |

---

## Building the .exe (Shadow PC Standalone)

```batch
cd BlueLineDispatchPro\desktop
pip install pyinstaller
pyinstaller build.spec
```

Output: `desktop/dist/BlueLineDispatchPro.exe`  
The exe is fully self-contained. Copy `dist/` folder + `audio/` folder + `models/` folder to run anywhere.

---

## How Plate / Ped Data Syncs

```
[LSPDFR / FivePD In-Game]
    Player runs plate or scans ped
           ↓
[FiveM Companion Client Script]
    Captures real game data (vehicle model, plate, owner name, DOB, etc.)
    Sends to server-side script via TriggerServerEvent
           ↓
[FiveM Companion Server Script]
    PerformHttpRequest → POST http://127.0.0.1:7623/api/plate
           ↓
[Desktop API Server (Flask)]
    Receives JSON, validates, stores in CADEngine
           ↓
[Desktop UI — Vehicle Lookup Tab]
    Auto-updates with real data in <1 second
```

---

## How Callouts Sync

```
[LSPDFR / FivePD]
    New callout triggered (Robbery, Traffic Stop, etc.)
           ↓
[Companion callout_hooks.lua]
    Captures: call type, location, priority, coords
    → TriggerServerEvent('bldp:newCall', callData)
           ↓
[Server main.lua]
    → POST http://127.0.0.1:7623/api/call
           ↓
[Desktop CAD — Active Calls Tab]
    Call auto-appears with all details
    Keyword listener may trigger dispatcher response audio
```

---

## Adding Your Own Dispatcher Audio

See `desktop/audio/AUDIO_INSTRUCTIONS.txt` for full details.

**Quick summary:**
- Record or download professional female dispatcher audio clips
- Apply the radio preset in Audacity (see instructions)
- Name files: `01.wav`, `02.wav`, `03.wav` ... up to as many as you want
- Drop into the correct category folder
- The app will randomly select from available files in that category

---

## Troubleshooting

**Keyword listener not detecting speech:**
- Check Settings → Input Device — ensure correct mic or VAC is selected
- Download and place the Vosk model (see Step 4 above)
- Try lowering the confidence threshold in Settings

**Plate data not appearing in CAD:**
- Ensure companion resource is running (`ensure bluedispatch-companion` in server.cfg)
- Check companion config.lua — `Config.DesktopAPIPort` must match desktop Settings → API Port
- Check desktop app's console/log for API errors
- Ensure firewall allows localhost port 7623

**Audio not playing:**
- Ensure .wav files exist in audio category folders
- Check Settings → Output Device
- Check Settings → Radio Effect Intensity (set to 0 to test raw audio)

**Scanner mode too frequent/infrequent:**
- Adjust Scanner Interval Min/Max in Settings tab

---

## Credits & Legal

- **Vosk** — Apache 2.0 — https://alphacephei.com/vosk/
- **CustomTkinter** — MIT — https://github.com/TomSchimansky/CustomTkinter
- **FiveM** — Cfx.re Terms of Service apply
- This tool is for **roleplay / entertainment purposes only**
- Do not use with real emergency services frequencies
- Audio files must be sourced with appropriate licensing

---

*BlueLineDispatchPro — Built for serious LSPDFR roleplayers.*
