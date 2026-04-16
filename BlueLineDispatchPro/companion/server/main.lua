--- BlueLineDispatchPro Companion — Server-Side Script
--- Receives events from client, relays to desktop CAD via HTTP
--- FiveM server-side Lua

local function dbg(msg)
    if Config.Debug then
        print(('[BLDP-Server] %s'):format(msg))
    end
end

-- ── HTTP Helper ──────────────────────────────────────────────────────────────

local function buildHeaders()
    local headers = { ['Content-Type'] = 'application/json' }
    if Config.APIKey and Config.APIKey ~= '' then
        headers['X-API-Key'] = Config.APIKey
    end
    return headers
end

local function postToCAD(endpoint, data, callback)
    local url = Config.APIBaseURL .. endpoint
    local body = json.encode(data)
    local headers = buildHeaders()

    dbg(('POST %s'):format(url))

    PerformHttpRequest(url, function(statusCode, responseText, responseHeaders)
        if statusCode == 200 or statusCode == 201 then
            dbg(('✓ %s → %d'):format(endpoint, statusCode))
            if callback then callback(true, responseText) end
        else
            if Config.Debug then
                print(('[BLDP-Server] ✗ HTTP Error %d for %s: %s'):format(
                    statusCode or 0, endpoint, responseText or 'no response'))
            end
            if callback then callback(false, responseText) end
        end
    end, 'POST', body, headers)
end

-- ── Ping / Heartbeat ─────────────────────────────────────────────────────────

AddEventHandler('bldp:server:ping', function(data)
    postToCAD('/ping', data)
end)

-- ── Plate Data ───────────────────────────────────────────────────────────────

AddEventHandler('bldp:server:plateData', function(plateData)
    if not plateData or not plateData.plate then
        dbg('Received empty plate data, ignoring')
        return
    end
    dbg(('Relaying plate data: %s'):format(plateData.plate))
    postToCAD('/plate', plateData)
end)

-- ── Ped Data ─────────────────────────────────────────────────────────────────

AddEventHandler('bldp:server:pedData', function(pedData)
    if not pedData then return end
    local name = (pedData.first_name or '') .. ' ' .. (pedData.last_name or '')
    dbg(('Relaying ped data: %s'):format(name))
    postToCAD('/ped', pedData)
end)

-- ── New Call ─────────────────────────────────────────────────────────────────

AddEventHandler('bldp:server:newCall', function(callData)
    if not callData then return end
    dbg(('Relaying new call: %s at %s'):format(
        callData.type or 'Unknown', callData.location or 'Unknown'))
    postToCAD('/call', callData)
end)

-- ── Update Call ───────────────────────────────────────────────────────────────

AddEventHandler('bldp:server:updateCall', function(callId, updates)
    if not callId then return end
    dbg(('Updating call: %s'):format(callId))
    local data = updates or {}
    data.call_id = callId
    postToCAD('/call/' .. callId, data)
end)

-- ── Unit Status ───────────────────────────────────────────────────────────────

AddEventHandler('bldp:server:unitStatus', function(unitData)
    if not unitData then return end
    dbg(('Unit status update: %s → %s'):format(
        unitData.unit_id or '?', unitData.status or '?'))
    postToCAD('/unit', unitData)
end)

-- ── BOLO ─────────────────────────────────────────────────────────────────────

AddEventHandler('bldp:server:bolo', function(boloData)
    if not boloData then return end
    dbg(('BOLO issued: %s'):format(boloData.subject or '?'))
    postToCAD('/bolo', boloData)
end)

-- ── Panic ────────────────────────────────────────────────────────────────────

AddEventHandler('bldp:server:panic', function(data)
    if not data then data = {} end
    dbg(('PANIC from unit: %s'):format(data.unit_id or 'UNKNOWN'))
    postToCAD('/panic', data)
end)

-- ── Startup ──────────────────────────────────────────────────────────────────

AddEventHandler('onResourceStart', function(resource)
    if resource ~= GetCurrentResourceName() then return end
    print('[BlueLineDispatchPro] Server companion started.')
    print(('[BlueLineDispatchPro] Desktop CAD API: %s'):format(Config.APIBaseURL))
    -- Test connectivity
    postToCAD('/status', {}, function(ok, response)
        if ok then
            print('[BlueLineDispatchPro] ✓ Desktop CAD is ONLINE')
        else
            print('[BlueLineDispatchPro] ✗ Desktop CAD is OFFLINE — start BlueLineDispatchPro.exe')
        end
    end)
end)

AddEventHandler('onResourceStop', function(resource)
    if resource ~= GetCurrentResourceName() then return end
    print('[BlueLineDispatchPro] Server companion stopped.')
end)
