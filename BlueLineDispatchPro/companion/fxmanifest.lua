--- BlueLineDispatchPro Companion Resource
--- FiveM Resource Manifest (fxmanifest.lua)
--- Compatible with FiveM, FivePD, and LSPDFR-style server mods

fx_version 'cerulean'
game 'gta5'

name 'bluedispatch-companion'
description 'BlueLineDispatchPro In-Game Companion — Bridges FiveM/LSPDFR data to desktop CAD'
author 'BlueLineDispatchPro'
version '1.0.0'
url 'https://github.com/BlueLineDispatchPro'

-- Load config first (shared between client and server)
shared_scripts {
    'config.lua',
}

-- Client-side scripts (hooks into in-game events, ALPR, callouts, etc.)
client_scripts {
    'client/main.lua',
    'client/plate_reader.lua',
    'client/callout_hooks.lua',
    'client/ped_scanner.lua',
}

-- Server-side scripts (HTTP relay to desktop CAD API)
server_scripts {
    'server/main.lua',
}

-- Dependencies (optional — comment out if not using these resources)
-- dependencies {
--     'FivePD',       -- If using FivePD for police callouts
--     'wraithars2',   -- If using Wraith ARS 2.x ALPR system
-- }

lua54 'yes'
