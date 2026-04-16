--- BlueLineDispatchPro Companion — Configuration
--- Edit this file to match your setup before starting the resource

Config = {}

-- ── Desktop App Connection ───────────────────────────────────────────────────
-- IP address of the machine running the BlueLineDispatchPro desktop app
-- If your FiveM server and desktop app are on the SAME machine (recommended): 127.0.0.1
-- If on different machines: use the desktop machine's local IP (e.g. 192.168.1.x)
Config.DesktopAPIHost = '127.0.0.1'

-- Port must match the API server port in the desktop app Settings (default: 7623)
Config.DesktopAPIPort = 7623

-- API Key — leave empty '' to disable authentication
-- If set, must match the API Key in the desktop app Settings
Config.APIKey = ''

-- ── Unit Identity ────────────────────────────────────────────────────────────
-- Your unit ID shown in the desktop CAD
Config.UnitID = '1-ADAM-12'
Config.OfficerName = 'Officer'
Config.Department = 'LSPD'
Config.Rank = 'Officer'

-- ── Feature Toggles ──────────────────────────────────────────────────────────
-- Enable/disable specific integrations

-- Plate reader integration (listens for custom plate read events)
Config.EnablePlateReader = true

-- Ped/person scanner integration
Config.EnablePedScanner = true

-- Callout hooks (FivePD / LSPDFR callout events)
Config.EnableCalloutHooks = true

-- Wraith ARS 2.x ALPR compatibility
Config.EnableWraithARS = true

-- FivePD native integration (set false if not using FivePD)
Config.EnableFivePD = true

-- Position updates (send unit coordinates to CAD for live map)
Config.EnablePositionUpdates = true
Config.PositionUpdateIntervalMs = 5000  -- How often to send position (ms)

-- ── Event Names ──────────────────────────────────────────────────────────────
-- Custom event names for plate reads (adjust to match your ALPR mod)
Config.PlateReadEvents = {
    'BLDP:plateRead',           -- Our own event
    'wk:ars2_ACGetOut',         -- Wraith ARS 2.x
    'wk:ars2_Scan',             -- Wraith ARS 2.x scan event
    'alpr:plateRead',           -- Generic ALPR event
    'lspdfr:plateRead',         -- LSPDFR bridge event
    'plate:query',              -- Generic query event
}

-- Ped scan events
Config.PedScanEvents = {
    'BLDP:pedScan',
    'lspdfr:pedScan',
    'fivepd:pedCheck',
}

-- ── CAD Commands ─────────────────────────────────────────────────────────────
-- In-game chat commands
Config.Commands = {
    sync = 'cad',          -- /cad — manual sync ping
    plate = 'plate',       -- /plate ABC123 — manual plate lookup
    ped = 'ped',           -- /ped — scan nearest ped
    status = 'status',     -- /status available — update your CAD status
    panic = 'panic',       -- /panic — trigger panic
    call = 'call',         -- /call — create a manual call in CAD
}

-- ── Debug ────────────────────────────────────────────────────────────────────
Config.Debug = false  -- Set true to see verbose console output

-- ── Internal (do not edit) ───────────────────────────────────────────────────
Config.APIBaseURL = ('http://%s:%d/api'):format(Config.DesktopAPIHost, Config.DesktopAPIPort)
Config.Version = '1.0.0'
