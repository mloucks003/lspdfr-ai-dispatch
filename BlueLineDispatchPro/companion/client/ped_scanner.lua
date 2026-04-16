--- BlueLineDispatchPro Companion — Ped Scanner
--- Captures NPC / ped information and sends to desktop CAD Person Lookup tab
--- Supports: /ped command, custom events, FivePD integration

local function dbg(msg)
    if Config.Debug then
        print(('[BLDP-Ped] %s'):format(msg))
    end
end

-- ── Name Generation (GTA doesn't expose NPC real names) ──────────────────────
-- Uses GTA's internal NPC model names to generate plausible names
-- Real name data comes from LSPDFR/FivePD mods that provide it via events

local FIRST_NAMES_M = {
    'James', 'Michael', 'Robert', 'David', 'William', 'Carlos', 'Luis', 'Marcus',
    'Derek', 'Shane', 'Trevor', 'Lance', 'Victor', 'Andre', 'Hector', 'Jerome',
    'Kyle', 'Brandon', 'Kevin', 'Aaron', 'Eric', 'Nathan', 'Jason', 'Ryan',
}
local FIRST_NAMES_F = {
    'Jennifer', 'Sarah', 'Ashley', 'Amanda', 'Stephanie', 'Michelle', 'Rachel',
    'Samantha', 'Angela', 'Karen', 'Lisa', 'Patricia', 'Maria', 'Sandra', 'Jessica',
    'Nicole', 'Brittany', 'Emily', 'Megan', 'Lauren', 'Crystal', 'Monica',
}
local LAST_NAMES = {
    'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Martinez', 'Rodriguez',
    'Davis', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson',
    'Martin', 'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Lopez', 'Gonzalez',
    'Robinson', 'Clark', 'Torres', 'Hill', 'Scott', 'Green', 'Adams', 'Baker',
}
local STREETS = {
    '112 South Rockford Dr', '445 Strawberry Ave', '7 Mile Highway',
    '820 Grove St', '3671 Whispymound Dr', '1500 Little Seoul Blvd',
    '290 Route 1', '45 Elgin Ave', '222 Del Perro Blvd',
}
local GANG_NAMES = { 'Ballas', 'Vagos', 'Lost MC', 'Marabunta Grande', 'Families' }

local function randomFrom(t) return t[math.random(#t)] end
local function randomDOB()
    local y = math.random(1960, 2000)
    local m = math.random(1, 12)
    local d = math.random(1, 28)
    return ('%04d-%02d-%02d'):format(y, m, d)
end

-- ── Ped Data Builder from GTA Entity ─────────────────────────────────────────

local function buildPedDataFromEntity(pedEntity)
    if not pedEntity or not DoesEntityExist(pedEntity) then return nil end

    -- Try to determine gender from ped model
    local model = GetEntityModel(pedEntity)
    local isMale = not IsPedModel(pedEntity, GetHashKey('mp_f_freemode_01'))
    local gender = isMale and 'M' or 'F'
    local firstNames = isMale and FIRST_NAMES_M or FIRST_NAMES_F

    -- Random but seeded on model hash for consistency (same NPC = same name)
    math.randomseed(model)
    local firstName = randomFrom(firstNames)
    local lastName  = randomFrom(LAST_NAMES)
    local dob       = randomDOB()
    local address   = randomFrom(STREETS)
    math.randomseed(os.time())  -- Reset seed

    -- Random record generation (weighted toward clean)
    local rand = math.random(100)
    local warrants        = rand <= 15
    local felony_warrants = rand <= 5
    local wanted          = rand <= 3
    local gang            = rand <= 10
    local priors          = gang and math.random(1, 8) or (warrants and math.random(1, 4) or 0)

    local pedData = {
        timestamp       = os.date('!%Y-%m-%dT%H:%M:%SZ'),
        first_name      = firstName,
        last_name       = lastName,
        dob             = dob,
        gender          = gender,
        ethnicity       = '',
        height_cm       = math.random(165, 195),
        weight_kg       = math.random(60, 100),
        hair_color      = randomFrom({'Black', 'Brown', 'Blonde', 'Red', 'Gray'}),
        eye_color       = randomFrom({'Brown', 'Blue', 'Green', 'Hazel'}),
        license_status  = (rand <= 8) and 'suspended' or 'valid',
        license_class   = 'C',
        license_expiry  = '2027-01-01',
        address         = address,
        phone           = ('555-%04d'):format(math.random(1000, 9999)),
        warrants        = warrants,
        felony_warrants = felony_warrants,
        wanted          = wanted,
        probation       = rand <= 12,
        parole          = rand <= 5,
        gang_affiliated = gang,
        gang_name       = gang and randomFrom(GANG_NAMES) or '',
        priors          = priors,
        prior_offenses  = {},
        notes           = '',
        source          = 'scanner',
    }

    -- Generate prior offenses list
    if priors > 0 then
        local offenses = {
            'Possession of Controlled Substance', 'Assault', 'Theft',
            'Resisting Arrest', 'DUI', 'Evading Police', 'Vandalism',
            'Trespassing', 'Illegal Firearms Possession', 'Grand Theft Auto',
        }
        for i = 1, math.min(priors, 5) do
            table.insert(pedData.prior_offenses, randomFrom(offenses))
        end
    end

    if felony_warrants then
        pedData.notes = 'ACTIVE FELONY WARRANTS. Exercise extreme caution.'
    elseif warrants then
        pedData.notes = 'Active misdemeanor warrants on file.'
    end

    return pedData
end

-- ── /ped Command ─────────────────────────────────────────────────────────────

RegisterCommand(Config.Commands.ped or 'ped', function(source, args, rawCommand)
    if not Config.EnablePedScanner then
        TriggerEvent('chat:addMessage', { args = { 'BlueLineCAD', 'Ped scanner is disabled.' } })
        return
    end

    local playerPed = PlayerPedId()
    local playerCoords = GetEntityCoords(playerPed)
    local targetPed = nil
    local minDist = 10.0

    -- Find nearest ped within 10 meters
    local peds = GetGamePool('CPed')
    for _, ped in ipairs(peds) do
        if ped ~= playerPed and IsEntityAPed(ped) and not IsPedAPlayer(ped) then
            local pedCoords = GetEntityCoords(ped)
            local dist = #(playerCoords - pedCoords)
            if dist < minDist then
                minDist = dist
                targetPed = ped
            end
        end
    end

    if not targetPed then
        TriggerEvent('chat:addMessage', {
            color = { 200, 100, 30 },
            args = { 'BlueLineCAD', 'No ped found within 10 meters.' }
        })
        return
    end

    dbg(('Scanning ped entity: %d (dist: %.1fm)'):format(targetPed, minDist))
    local pedData = buildPedDataFromEntity(targetPed)

    if pedData then
        TriggerServerEvent('bldp:server:pedData', pedData)
        local name = pedData.first_name .. ' ' .. pedData.last_name
        local flags = pedData.warrants and ' [WARRANTS]' or ''
        TriggerEvent('chat:addMessage', {
            color = { 30, 111, 217 },
            args = { 'BlueLineCAD', ('Ped scanned: %s%s — Check CAD for details.'):format(name, flags) }
        })
    end
end, false)

-- ── Custom Ped Scan Events ────────────────────────────────────────────────────

AddEventHandler('BLDP:pedScan', function(pedData)
    if not Config.EnablePedScanner then return end
    if not pedData then return end
    dbg('Custom ped scan event received')
    pedData.timestamp = pedData.timestamp or os.date('!%Y-%m-%dT%H:%M:%SZ')
    pedData.source = pedData.source or 'event'
    TriggerServerEvent('bldp:server:pedData', pedData)
end)

-- ── FivePD Integration ────────────────────────────────────────────────────────

if Config.EnableFivePD then
    AddEventHandler('fivepd:pedCheck', function(data)
        if not Config.EnablePedScanner then return end
        if not data then return end
        dbg('FivePD ped check received')

        local pedData = {
            timestamp       = os.date('!%Y-%m-%dT%H:%M:%SZ'),
            first_name      = data.firstName  or data.first_name  or '',
            last_name       = data.lastName   or data.last_name   or '',
            dob             = data.dob        or '',
            gender          = data.gender     or 'M',
            license_status  = data.licenseStatus or 'valid',
            warrants        = data.hasWarrants or data.warrants or false,
            felony_warrants = data.hasFelonyWarrants or data.felony_warrants or false,
            wanted          = data.isWanted   or data.wanted or false,
            priors          = data.priors     or 0,
            notes           = data.notes      or '',
            source          = 'fivepd',
        }
        TriggerServerEvent('bldp:server:pedData', pedData)
    end)
end

-- ── Export ────────────────────────────────────────────────────────────────────

exports('submitPed', function(pedData)
    if not pedData then return false end
    pedData.timestamp = pedData.timestamp or os.date('!%Y-%m-%dT%H:%M:%SZ')
    pedData.source = pedData.source or 'export'
    TriggerServerEvent('bldp:server:pedData', pedData)
    return true
end)

exports('scanNearestPed', function(maxDistance)
    maxDistance = maxDistance or 10.0
    TriggerEvent('BLDP:pedScan', nil)  -- Trigger via command logic
    return true
end)
