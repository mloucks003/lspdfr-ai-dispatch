--- BlueLineDispatchPro Companion — Callout Hooks
--- Hooks into FivePD callout events and generic LSPDFR-style events
--- Sends call data to the desktop CAD automatically

local _activeCallId = nil  -- Track the current in-progress call ID

local function dbg(msg)
    if Config.Debug then
        print(('[BLDP-Callout] %s'):format(msg))
    end
end

local function getStreetName(coords)
    if not coords then return 'Unknown Location' end
    local streetHash, _ = GetStreetNameAtCoord(coords.x, coords.y, coords.z)
    return GetStreetNameFromHashKey(streetHash) or 'Unknown Location'
end

local function makeCallId()
    return tostring(math.random(10000, 99999))
end

-- ── Callout Priority Mapping ──────────────────────────────────────────────────

local PRIORITY_MAP = {
    ['10-99'] = 1, ['officer down'] = 1, ['shots fired'] = 1,
    ['robbery'] = 2, ['carjacking'] = 2, ['assault'] = 2, ['shooting'] = 2,
    ['traffic stop'] = 4, ['traffic accident'] = 3, ['vehicle pursuit'] = 2,
    ['burglary'] = 2, ['domestic'] = 3, ['disturbance'] = 3,
    ['code 3'] = 2, ['code 2'] = 3, ['code 1'] = 4,
}

local function guessPriority(callType)
    local lower = callType:lower()
    for keyword, priority in pairs(PRIORITY_MAP) do
        if lower:find(keyword) then
            return priority
        end
    end
    return 3  -- Default medium priority
end

-- ── FivePD Integration ────────────────────────────────────────────────────────

if Config.EnableFivePD then
    -- FivePD: New callout assigned to officer
    AddEventHandler('fivepd:calloutCreated', function(data)
        if not Config.EnableCalloutHooks then return end
        if not data then return end
        dbg(('FivePD callout created: %s'):format(data.calloutName or '?'))

        local coords = data.position or data.coords or nil
        local location = coords and getStreetName(coords) or (data.location or 'Unknown')
        _activeCallId = data.callId or makeCallId()

        TriggerServerEvent('bldp:server:newCall', {
            call_id     = _activeCallId,
            type        = data.calloutName or data.type or 'Unknown Callout',
            code        = data.code or '',
            priority    = data.priority or guessPriority(data.calloutName or ''),
            status      = 'dispatched',
            location    = location,
            description = data.calloutDescription or data.description or '',
            coords      = coords and { x = coords.x, y = coords.y, z = coords.z } or { x = 0, y = 0, z = 0 },
            caller      = data.caller or 'Dispatch',
            assigned_units = { Config.UnitID },
            source      = 'fivepd',
        })
    end)

    -- FivePD: Callout accepted / officer en route
    AddEventHandler('fivepd:calloutAccepted', function(callId)
        if not Config.EnableCalloutHooks then return end
        local cid = callId or _activeCallId
        if not cid then return end
        TriggerServerEvent('bldp:server:updateCall', cid, { status = 'dispatched' })
    end)

    -- FivePD: Officer arrived on scene
    AddEventHandler('fivepd:calloutOnScene', function(callId)
        if not Config.EnableCalloutHooks then return end
        local cid = callId or _activeCallId
        if not cid then return end
        TriggerServerEvent('bldp:server:updateCall', cid, { status = 'on-scene' })
    end)

    -- FivePD: Callout ended / cleared
    AddEventHandler('fivepd:calloutEnded', function(callId)
        if not Config.EnableCalloutHooks then return end
        local cid = callId or _activeCallId
        if not cid then return end
        TriggerServerEvent('bldp:server:updateCall', cid, { status = 'closed' })
        _activeCallId = nil
    end)

    -- FivePD: BOLO / warrant issued
    AddEventHandler('fivepd:boloIssued', function(data)
        if not data then return end
        TriggerServerEvent('bldp:server:bolo', {
            type        = data.type or 'person',
            subject     = data.subject or data.name or '',
            description = data.description or '',
            reason      = 'warrant',
            plate       = data.plate or '',
            priority    = data.priority or 2,
            issued_by   = Config.UnitID,
        })
    end)
end

-- ── Generic LSPDFR-Bridge Events ─────────────────────────────────────────────
-- For servers using LSPDFR-compatible event bridges

AddEventHandler('BLDP:newCall', function(callData)
    if not Config.EnableCalloutHooks then return end
    if not callData then return end
    dbg(('Custom call event: %s'):format(callData.type or '?'))
    callData.source = callData.source or 'bridge'
    callData.assigned_units = callData.assigned_units or { Config.UnitID }
    TriggerServerEvent('bldp:server:newCall', callData)
end)

AddEventHandler('BLDP:updateCall', function(callId, updates)
    if not callId then return end
    TriggerServerEvent('bldp:server:updateCall', callId, updates)
end)

AddEventHandler('BLDP:issueBOLO', function(boloData)
    if not boloData then return end
    boloData.issued_by = boloData.issued_by or Config.UnitID
    TriggerServerEvent('bldp:server:bolo', boloData)
end)

-- ── Traffic Stop Tracking ─────────────────────────────────────────────────────

local _trafficStopId = nil

-- Detect when officer initiates a traffic stop via game flag
CreateThread(function()
    while true do
        Wait(3000)
        if not Config.EnableCalloutHooks then goto continue end

        local ped = PlayerPedId()
        -- Check if officer has initiated a traffic stop (GTA native check)
        -- This is a simplistic check; integrate with actual police mod for accuracy
        local vehicle = GetVehiclePedIsIn(ped, false)
        if vehicle == 0 then goto continue end

        -- Check for police lights on player vehicle (indicator of traffic stop)
        local hasLights = IsVehicleSirenOn(vehicle)
        if hasLights and not _trafficStopId then
            local coords = GetEntityCoords(ped)
            local location = getStreetName(coords)
            _trafficStopId = makeCallId()
            TriggerServerEvent('bldp:server:newCall', {
                call_id     = _trafficStopId,
                type        = 'Traffic Stop',
                code        = '10-38',
                priority    = 4,
                status      = 'on-scene',
                location    = location,
                description = 'Officer-initiated traffic stop',
                coords      = { x = coords.x, y = coords.y, z = coords.z },
                assigned_units = { Config.UnitID },
                source      = 'auto',
            })
            dbg(('Traffic stop auto-created: %s'):format(_trafficStopId))
        elseif not hasLights and _trafficStopId then
            TriggerServerEvent('bldp:server:updateCall', _trafficStopId, { status = 'clearing' })
            _trafficStopId = nil
            dbg('Traffic stop cleared')
        end

        ::continue::
    end
end)

-- ── Exports ──────────────────────────────────────────────────────────────────

exports('createCall', function(callData)
    if not callData then return nil end
    callData.call_id = callData.call_id or makeCallId()
    callData.source = 'export'
    callData.assigned_units = callData.assigned_units or { Config.UnitID }
    TriggerServerEvent('bldp:server:newCall', callData)
    return callData.call_id
end)

exports('updateCall', function(callId, updates)
    TriggerServerEvent('bldp:server:updateCall', callId, updates)
end)

exports('issueBOLO', function(boloData)
    boloData.issued_by = boloData.issued_by or Config.UnitID
    TriggerServerEvent('bldp:server:bolo', boloData)
end)
