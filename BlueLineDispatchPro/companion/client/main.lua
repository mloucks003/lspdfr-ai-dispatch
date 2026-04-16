--- BlueLineDispatchPro Companion — Client Main Script
--- Handles: ping/heartbeat, commands, position updates, panic

local _pingInterval = nil
local _positionInterval = nil
local _isInitialized = false

local function dbg(msg)
    if Config.Debug then
        print(('[BLDP-Client] %s'):format(msg))
    end
end

-- ── Utility: Get unit data for this session ──────────────────────────────────

local function getMyUnitData()
    local ped = PlayerPedId()
    local coords = GetEntityCoords(ped)
    return {
        unit_id    = Config.UnitID,
        name       = Config.OfficerName,
        department = Config.Department,
        rank       = Config.Rank,
        status     = 'available',
        coords     = { x = coords.x, y = coords.y, z = coords.z },
        vehicle    = '',
    }
end

-- ── Heartbeat Ping ───────────────────────────────────────────────────────────
-- Tells the desktop app we are connected

local function sendPing()
    local data = getMyUnitData()
    data.timestamp = os.time()
    TriggerServerEvent('bldp:server:ping', data)
    dbg('Ping sent')
end

-- ── Position Updates ─────────────────────────────────────────────────────────

local function sendPositionUpdate()
    if not Config.EnablePositionUpdates then return end
    local ped = PlayerPedId()
    local coords = GetEntityCoords(ped)
    local inVehicle = IsPedInAnyVehicle(ped, false)
    local vehicleName = ''
    if inVehicle then
        local veh = GetVehiclePedIsIn(ped, false)
        local model = GetEntityModel(veh)
        vehicleName = GetDisplayNameFromVehicleModel(model)
    end

    TriggerServerEvent('bldp:server:unitStatus', {
        unit_id  = Config.UnitID,
        name     = Config.OfficerName,
        status   = 'available',
        coords   = { x = coords.x, y = coords.y, z = coords.z },
        vehicle  = vehicleName,
    })
end

-- ── Initialization ───────────────────────────────────────────────────────────

local function initialize()
    if _isInitialized then return end
    _isInitialized = true

    -- Send initial ping immediately
    sendPing()

    -- Heartbeat every 30 seconds
    _pingInterval = SetInterval(function()
        sendPing()
    end, 30000)

    -- Position updates
    if Config.EnablePositionUpdates then
        _positionInterval = SetInterval(function()
            sendPositionUpdate()
        end, Config.PositionUpdateIntervalMs or 5000)
    end

    print('[BlueLineDispatchPro] Client companion initialized')
    print(('[BlueLineDispatchPro] Unit: %s | Dept: %s'):format(Config.UnitID, Config.Department))
end

-- Initialize when resource starts
AddEventHandler('onClientResourceStart', function(resource)
    if resource ~= GetCurrentResourceName() then return end
    -- Small delay to let server-side start first
    SetTimeout(2000, initialize)
end)

-- ── Commands ─────────────────────────────────────────────────────────────────

-- /cad — manual sync
RegisterCommand(Config.Commands.sync or 'cad', function(source, args, rawCommand)
    sendPing()
    TriggerEvent('chat:addMessage', {
        color = { 30, 111, 217 },
        multiline = true,
        args = { 'BlueLineCAD', 'Syncing with desktop CAD...' }
    })
end, false)

-- /status <status> — update CAD status
RegisterCommand(Config.Commands.status or 'status', function(source, args, rawCommand)
    local statusInput = args[1] and args[1]:lower() or 'available'
    local statusMap = {
        ['available'] = 'available', ['10-8'] = 'available', ['av'] = 'available',
        ['busy']      = 'busy',      ['10-6'] = 'busy',
        ['scene']     = 'on-scene',  ['10-23'] = 'on-scene', ['onscene'] = 'on-scene',
        ['code6']     = 'code-6',    ['c6'] = 'code-6',
        ['oos']       = 'out-of-service',
    }
    local status = statusMap[statusInput] or statusInput
    TriggerServerEvent('bldp:server:unitStatus', {
        unit_id = Config.UnitID,
        status  = status,
    })
    TriggerEvent('chat:addMessage', {
        color = { 30, 200, 90 },
        args = { 'BlueLineCAD', ('Status updated to: %s'):format(status:upper()) }
    })
end, false)

-- /panic — trigger panic from command
RegisterCommand(Config.Commands.panic or 'panic', function(source, args, rawCommand)
    TriggerEvent('bldp:client:panic')
end, false)

-- /call <description> — create manual call
RegisterCommand(Config.Commands.call or 'call', function(source, args, rawCommand)
    local description = table.concat(args, ' ')
    if description == '' then
        TriggerEvent('chat:addMessage', {
            args = { 'BlueLineCAD', 'Usage: /call <description>' }
        })
        return
    end
    local ped = PlayerPedId()
    local coords = GetEntityCoords(ped)
    local streetHash, _ = GetStreetNameAtCoord(coords.x, coords.y, coords.z)
    local streetName = GetStreetNameFromHashKey(streetHash) or 'Unknown Location'

    TriggerServerEvent('bldp:server:newCall', {
        type        = 'Manual Call',
        description = description,
        location    = streetName,
        priority    = 3,
        status      = 'pending',
        coords      = { x = coords.x, y = coords.y, z = coords.z },
        caller      = Config.UnitID,
        source      = 'manual',
    })
    TriggerEvent('chat:addMessage', {
        color = { 30, 111, 217 },
        args = { 'BlueLineCAD', ('Call created: %s'):format(description) }
    })
end, false)

-- ── Panic Event ───────────────────────────────────────────────────────────────

AddEventHandler('bldp:client:panic', function()
    local ped = PlayerPedId()
    local coords = GetEntityCoords(ped)
    TriggerServerEvent('bldp:server:panic', {
        unit_id   = Config.UnitID,
        name      = Config.OfficerName,
        coords    = { x = coords.x, y = coords.y, z = coords.z },
        timestamp = os.time(),
    })
    -- Visual/audio panic effect in-game (optional)
    BeginTextCommandThefeedPost('STRING')
    AddTextComponentSubstringPlayerName('🚨 PANIC BUTTON ACTIVATED — All units respond!')
    EndTextCommandThefeedPostTicker(false, true)
    dbg('Panic triggered!')
end)

-- ── Cleanup ───────────────────────────────────────────────────────────────────

AddEventHandler('onClientResourceStop', function(resource)
    if resource ~= GetCurrentResourceName() then return end
    if _pingInterval then ClearInterval(_pingInterval) end
    if _positionInterval then ClearInterval(_positionInterval) end
    TriggerServerEvent('bldp:server:unitStatus', {
        unit_id = Config.UnitID,
        status  = 'out-of-service',
    })
    print('[BlueLineDispatchPro] Client companion stopped.')
end)
