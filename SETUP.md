# LSPDFR AI Dispatch — Setup Guide

## What's in the Zip

```
LSPDFRDispatch/
├── DispatchRadio/
│   ├── DispatchRadio.exe    ← The all-in-one desktop app (backend + radio)
│   └── config.ini           ← Your settings (OpenAI key goes here)
├── Plugins/
│   ├── LSPDFRDispatch.dll   ← LSPDFR plugin (reads game data)
│   ├── Newtonsoft.Json.dll  ← Plugin dependency
│   └── LSPDFRDispatch.ini   ← Plugin settings
└── INSTALL.txt
```

## Installation (2 minutes)

### 1. Plugin — Copy to GTA V

Copy everything from the `Plugins/` folder into your GTA V `Plugins/` folder:

```
GTA V/
  Plugins/
    LSPDFRDispatch.dll        ← new
    Newtonsoft.Json.dll        ← new
    LSPDFRDispatch.ini         ← new
```

### 2. Desktop App — Put Anywhere

Put the `DispatchRadio/` folder wherever you want (Desktop, Documents, etc.).

Edit `config.ini` and add your OpenAI API key:

```ini
[General]
OpenAIApiKey=sk-your-key-here
ApiKey=dispatch-secret
OfficerCallsign=1-Adam-12
Port=8000
```

### 3. Run It

1. Run `DispatchRadio.exe` — this starts the backend server + dispatch radio
2. Open `http://localhost:8000` in your browser for the CAD
3. Launch GTA V via RagePluginHook
4. Go on duty in LSPDFR
5. Say "dispatch" to talk to your AI dispatcher

## Configuration

### config.ini (Desktop App)

| Setting | Description |
|---------|-------------|
| `OpenAIApiKey` | Your OpenAI API key (required for voice) |
| `ApiKey` | Shared secret between app and plugin (must match) |
| `OfficerCallsign` | Your unit callsign (e.g. 1-Adam-12) |
| `Port` | Backend port (default 8000) |
| `WakeThreshold` | Mic sensitivity for wake word (lower = more sensitive) |
| `SilenceTimeout` | Seconds of silence before ending a command |

### LSPDFRDispatch.ini (Plugin)

| Setting | Description |
|---------|-------------|
| `BackendUrl` | Must point to the desktop app (default ws://localhost:8000) |
| `ApiKey` | Must match the desktop app's ApiKey |
| `OfficerCallsign` | Your callsign |
| `ScanRadius` | How far to scan for peds/vehicles (game units) |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Plugin not loading | Check RagePluginHook console for `[LSPDFRDispatch]` messages |
| "Connection refused" | Make sure DispatchRadio.exe is running before launching GTA V |
| No voice response | Check that your OpenAI API key is set in config.ini |
| CAD not loading | Open http://localhost:8000 — the backend serves the CAD directly |
| Wrong callsign | Edit both config.ini and LSPDFRDispatch.ini |

## Updating

When a new version is released, just download the new zip and replace the files.
Your `config.ini` and `dispatch.db` (database) are preserved — they're not in the zip.
