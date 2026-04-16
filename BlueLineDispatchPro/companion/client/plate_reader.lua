--- BlueLineDispatchPro Companion — Plate Reader Integration
--- Hooks into ALPR events from Wraith ARS, FivePD, and custom LSPDFR bridges
--- Sends real vehicle/plate data to the desktop CAD

local function dbg(msg)
    if Config.Debug then
        print(('[BLDP-Plate] %s'):format(msg))
    end
end

-- ── Plate Data Builder ───────────────────────────────────────────────────────

local function buildPlateData(plate, vehicle, owner, source)
    source = source or 'alpr'
    local plateData = {
        timestamp = os.date('!%Y-%m-%dT%H:%M:%SZ'),
        plate     = plate or '??????',
        state     = 'San Andreas',
        stolen    = false,
        flagged   = false,
        source    = source,
        vehicle   = {
            make  = '',
            model = '',
            year  = 0,
            color = '',
            vin   = '',
            type  = '',
        },
        registration = {
            status  = 'unknown',
            expiry  = '',
            insurance = 'unknown',
        },
        owner = {
            first_name      = '',
            last_name       = '',
            dob             = '',
            license_status  = 'unknown',
            license_class   = 'C',
            address         = '',
            phone           = '',
            warrants        = false,
            felony_warrants = false,
            wanted          = false,
            gang_affiliated = false,
            gang_name       = '',
            priors          = 0,
            notes           = '',
        },
    }

    -- Merge vehicle data if provided
    if vehicle and type(vehicle) == 'table' then
        for k, v in pairs(vehicle) do
            if plateData.vehicle[k] ~= nil or true then
                plateData.vehicle[k] = v
            end
        end
        plateData.stolen  = vehicle.stolen  or false
        plateData.flagged = vehicle.flagged or false
    end

    -- Merge owner data if provided
    if owner and type(owner) == 'table' then
        for k, v in pairs(owner) do
            plateData.owner[k] = v
        end
        plateData.flagged = plateData.flagged or owner.warrants or owner.felony_warrants or owner.wanted or false
    end

    return plateData
end

-- ── GTA Vehicle Info Extractor ────────────────────────────────────────────────
-- Extracts what we can from the GTA game entity (without LSPDFR C# access)

local VEHICLE_TYPES = {
    [0] = 'automobile', [1] = 'plane', [2] = 'trailer',
    [3] = 'quadbike',   [5] = 'boat',  [6] = 'motorcycle',
    [7] = 'bicycle',    [8] = 'helicopter', [9] = 'blimp',
    [10] = 'emergency', [11] = 'train', [12] = 'submarine',
    [13] = 'amphibious', [14] = 'submarinecar',
}

local COLORS = {
    [0] = 'Black', [1] = 'Black (Graphite)', [2] = 'Black (Steel Gray)',
    [3] = 'Black (Shadow)', [4] = 'Black (Dark)', [11] = 'Red',
    [27] = 'Blue', [64] = 'White', [122] = 'Gray', [131] = 'Green', [138] = 'Yellow',
}

local function getVehicleInfoFromEntity(veh)
    if not DoesEntityExist(veh) then return {} end

    local model = GetEntityModel(veh)
    local modelName = GetDisplayNameFromVehicleModel(model)
    local makeHash = GetMakeNameFromVehicleModel(model)
    local plate = GetVehicleNumberPlateText(veh)
    local colorIdx, _ = GetVehicleColours(veh)
    local color = COLORS[colorIdx] or ('Color #%d'):format(colorIdx)
    local vehTypeId = GetVehicleType(veh)
    local vehType = VEHICLE_TYPES[vehTypeId] or 'automobile'

    return {
        make  = makeHash or 'Unknown',
        model = modelName or 'Unknown',
        color = color,
        type  = vehType,
        plate = plate,
        year  = math.random(2015, 2023),  -- GTA doesn't expose real year
        vin   = ('VIN' .. tostring(math.random(100000, 999999))),
    }
end

-- ── Manual Plate Command ──────────────────────────────────────────────────────

RegisterCommand(Config.Commands.plate or 'plate', function(source, args, rawCommand)
    local plateInput = args[1]
    if not plateInput then
        -- Try to get plate from vehicle the player is looking at
        local ped = PlayerPedId()
        local veh = GetVehiclePedIsIn(ped, false)
        if veh == 0 then
            -- Look at nearest vehicle
            local coords = GetEntityCoords(ped)
            veh = GetClosestVehicle(coords.x, coords.y, coords.z, 10.0, 0, 70)
        end
        if veh and veh ~= 0 then
            plateInput = GetVehicleNumberPlateText(veh):gsub('%s+', '')
        end
    end

    if not plateInput or plateInput == '' then
        TriggerEvent('chat:addMessage', {
            args = { 'BlueLineCAD', 'Usage: /plate <LICENSE_PLATE>' }
        })
        return
    end

    plateInput = plateInput:upper():gsub('%s+', '')
    dbg(('Manual plate query: %s'):format(plateInput))

    -- Try to find the vehicle entity with this plate
    local vehInfo = {}
    local ped = PlayerPedId()
    local coords = GetEntityCoords(ped)

    -- Check vehicles nearby for matching plate
    local vehicles = GetGamePool('CVehicle')
    for _, veh in ipairs(vehicles) do
        local vehPlate = GetVehicleNumberPlateText(veh):gsub('%s+', ''):upper()
        if vehPlate == plateInput then
            vehInfo = getVehicleInfoFromEntity(veh)
            break
        end
    end

    local plateData = buildPlateData(plateInput, vehInfo, nil, 'manual')
    TriggerServerEvent('bldp:server:plateData', plateData)

    TriggerEvent('chat:addMessage', {
        color = { 30, 111, 217 },
        args = { 'BlueLineCAD', ('Plate query sent to CAD: %s'):format(plateInput) }
    })
end, false)

-- ── Wraith ARS 2.x Integration ────────────────────────────────────────────────

if Config.EnableWraithARS then
    -- Wraith ARS fires this event when vehicle exits ALPR camera range (full scan)
    AddEventHandler('wk:ars2_ACGetOut', function(veh, plate, isFront)
        if not Config.EnablePlateReader then return end
        dbg(('Wraith ARS scan: %s'):format(plate or '?'))

        local vehInfo = getVehicleInfoFromEntity(veh)
        vehInfo.plate = plate

        local plateData = buildPlateData(plate, vehInfo, nil, 'wraith')
        TriggerServerEvent('bldp:server:plateData', plateData)
    end)

    -- Wraith ARS manual scan
    AddEventHandler('wk:ars2_Scan', function(veh, plate)
        if not Config.EnablePlateReader then return end
        dbg(('Wraith ARS manual scan: %s'):format(plate or '?'))

        local vehInfo = getVehicleInfoFromEntity(veh)
        vehInfo.plate = plate

        local plateData = buildPlateData(plate, vehInfo, nil, 'wraith')
        TriggerServerEvent('bldp:server:plateData', plateData)
    end)
end

-- ── Generic Plate Read Event ──────────────────────────────────────────────────
-- Fires when any script triggers the BLDP plate read event directly

AddEventHandler('BLDP:plateRead', function(plateData)
    if not Config.EnablePlateReader then return end
    if not plateData then return end

    dbg(('Custom plate event received: %s'):format(plateData.plate or '?'))

    -- If it's a full plate data object, send it directly
    if plateData.vehicle or plateData.owner then
        plateData.source = plateData.source or 'lspdfr'
        plateData.timestamp = plateData.timestamp or os.date('!%Y-%m-%dT%H:%M:%SZ')
        TriggerServerEvent('bldp:server:plateData', plateData)
    else
        -- Minimal data — just plate string
        local plate = type(plateData) == 'string' and plateData or plateData.plate
        if plate then
            TriggerServerEvent('bldp:server:plateData', buildPlateData(plate, {}, nil, 'event'))
        end
    end
end)

-- ── FivePD Integration ────────────────────────────────────────────────────────

if Config.EnableFivePD then
    -- FivePD fires 'fivepd:vehicleCheck' when officer runs a plate
    AddEventHandler('fivepd:vehicleCheck', function(data)
        if not Config.EnablePlateReader then return end
        if not data then return end
        dbg('FivePD vehicle check received')

        local plate = data.plate or data.licensePlate or ''
        local plateData = buildPlateData(plate, {
            make  = data.make  or data.vehicleMake  or '',
            model = data.model or data.vehicleModel or '',
            color = data.color or data.vehicleColor or '',
            stolen = data.stolen or false,
        }, {
            first_name      = data.ownerFirstName or data.firstName or '',
            last_name       = data.ownerLastName  or data.lastName  or '',
            dob             = data.dob or '',
            warrants        = data.hasWarrants or false,
            felony_warrants = data.hasFelonyWarrants or false,
            priors          = data.priors or 0,
        }, 'fivepd')

        TriggerServerEvent('bldp:server:plateData', plateData)
    end)
end

-- ── Export for Other Resources ────────────────────────────────────────────────
-- Other resources can call: exports['bluedispatch-companion']:submitPlate(plateData)

exports('submitPlate', function(plateData)
    if not plateData then return false end
    plateData.source = plateData.source or 'export'
    plateData.timestamp = plateData.timestamp or os.date('!%Y-%m-%dT%H:%M:%SZ')
    TriggerServerEvent('bldp:server:plateData', plateData)
    return true
end)

exports('submitPlateSimple', function(plate, vehEntity)
    if not plate then return false end
    local vehInfo = vehEntity and getVehicleInfoFromEntity(vehEntity) or {}
    TriggerServerEvent('bldp:server:plateData', buildPlateData(plate, vehInfo, nil, 'export'))
    return true
end)
