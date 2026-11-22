-- Dungeon Maps 5 - a Turtle-WoW-style dungeon map for WoW: Forever. Standalone (no other addon
-- needed); its data (Data.lua) comes from Forever Dungeon Routes (MIT), see the header there.
--
-- Inside a dungeon or raid, the map key (whatever is bound to "Toggle World Map", G here) opens one
-- big map of the dungeon floor instead of the outdoor zone. Outside instances the key is left alone.
-- "World Map" opens the normal map on the dungeon's zone; "Dungeon Map" on the world map comes back.
--
-- Where the dots come from. WoW: Forever gives addons no coordinates inside instances (tested in
-- Ragefire Chasm, build 1.60.1.70959: UnitPosition, C_Map.GetPlayerMapPosition, GetBestMapForUnit and
-- GetPlayerFacing answer nothing; the engine's UnitPositionFrame draws nothing; nameplate units are
-- secret). What the game does reveal:
--   * YOU, at the latest landmark: the entrance when you zone in, a boss's spot when its encounter
--     starts, the named room you walk into (the sub-zone). Older landmarks fade.
--   * TEAMMATES running this addon or Forever Dungeon Routes: the room they broadcast (addon
--     messages, Forever Dungeon Routes' "FDRGroup" format, so both addons understand each other).
--   * TEAMMATES without either: range checks. Within ~28 yards (CheckInteractDistance 4) they are
--     drawn beside you; within ~40 yards (UnitInRange), beside you and faded.
-- Bosses: numbered skulls at Forever's boss spots, hover for the name, grey once killed. (Skulls
-- painted into some classic map art are the Cataclysm versions' bosses.)

local _, ns = ...

local MAP_W, MAP_H, TILE = 1002, 668, 256
local BAR_H, PAD = 30, 8
local ADDON_PATH = "Interface\\AddOns\\DungeonMaps\\"
local BLIP_ATLAS = "WhiteCircle-RaidBlips"
local SKULL = "Interface\\TargetingFrame\\UI-TargetingFrame-Skull"
local DOT, ME_DOT, BOSS = 14, 18, 24   -- marker sizes in map pixels
local SPREAD = 20                      -- people sharing a spot sit on a ring this far from it
local NEAR_RING = 22                   -- teammates found by range sit this far from you
local POLL = 0.5                       -- seconds between updates
local MANUAL_HOLD = 20                 -- after picking a floor by hand, auto-follow waits this long
local FRESH = 90                       -- a landmark this many seconds old is still "you are here"
local OLD_FADE = 0.55                  -- alpha of a dot placed from an old landmark / last room
local FAR_FADE = 0.7                   -- alpha of a teammate placed from the 40-yard check
local LEGEND_ROW, LEGEND_MAX = 18, 10
local SIZE_MIN, SIZE_MAX = 0.5, 2.5    -- the map settings' size sliders (your arrow, teammates, bosses)
local RUN_MAX_AGE = 3 * 3600           -- boss kills older than this belong to an old run
local PREFIX = "FDRGroup"              -- Forever Dungeon Routes' group channel (same message format)
local STATE_GAP = 2                    -- seconds between two room messages

DungeonMapsDB = DungeonMapsDB or {}
DungeonMapsCharDB = DungeonMapsCharDB or {}

BINDING_HEADER_DUNGEONMAPS = "Dungeon Maps"
BINDING_NAME_DUNGEONMAPS_TOGGLE = "Dungeon map (in dungeons) / world map"

local events = CreateFrame("Frame")
local bindingsPending = false

local map              -- the map window (built on first use)
local backButton       -- "Dungeon Map" on Blizzard's world map
local dungeon          -- the dungeon shown (an entry of ns.Dungeons)
local floors = {}      -- its floor uiMapIDs
local floorIndex       -- index into floors
local manualAt = 0     -- GetTime() of the last floor picked by hand
local lastRoom = {}    -- [short name] = { room, key, t, now } last named room seen, per person
local landmark         -- { key, floor, u, v, label, t, kind }: where you were last seen for sure
local landmarkCount = 0 -- goes up with every new landmark (the live tracker watches it)
local wingPick = {}    -- [instanceID] = dungeon key picked (instances with several wings)
local members = {}     -- [sender] = { key, room name } from group messages
local activeEncounter -- { key, index }: only while an encounter is active
local worldInstance   -- last observed instance, so duplicate zone events aren't new runs
local enteringDead = false -- captured before loading; the client may resurrect us at the door

-- A size setting (Settings / the map's gear menu): 0.5x to 2.5x, in tenths.
local function sizeOf(key)
	local v = tonumber(DungeonMapsDB and DungeonMapsDB[key]) or 1
	return math.max(SIZE_MIN, math.min(SIZE_MAX, math.floor(v * 10 + 0.5) / 10))
end

local function say(msg)
	DEFAULT_CHAT_FRAME:AddMessage("|cffffd24dDungeon Maps:|r " .. msg)
end

-- Plain value or nil: in restricted instances Forever hands addons secret values, which can't be
-- compared or used; they count as unknown.
local isSecret = issecretvalue or function() return false end
local function plain(v)
	if isSecret(v) then return nil end
	return v
end

local function call(fn, ...)
	if not fn then return nil end
	local r = { pcall(fn, ...) }
	if not r[1] then return nil end
	return select(2, unpack(r))
end

local function inDungeon()
	local inside, kind = IsInInstance()
	inside, kind = plain(inside), plain(kind)
	return inside == true and (kind == "party" or kind == "raid")
end

local function instanceID()
	return plain((select(8, GetInstanceInfo())))
end

local function shortName(name)
	if type(name) ~= "string" then return nil end
	return Ambiguate and Ambiguate(name, "short") or name:match("^[^-]+")
end

local function classColor(unit)
	local _, class = UnitClass(unit)
	class = plain(class)
	local c = class and RAID_CLASS_COLORS and RAID_CLASS_COLORS[class]
	if c then return c.r, c.g, c.b end
	return 0.8, 0.8, 0.8
end

local function groupUnits()
	local list = {}
	if IsInRaid() then
		for i = 1, GetNumGroupMembers() do list[#list + 1] = "raid" .. i end
	else
		for i = 1, GetNumSubgroupMembers() do list[#list + 1] = "party" .. i end
	end
	return list
end

---------------------------------------------------------------------------------------------------
-- Data lookups
---------------------------------------------------------------------------------------------------

local byKey, byInstance = {}, {}
for _, d in ipairs(ns.Dungeons) do
	byKey[d.key] = d
	byInstance[d.instanceID] = byInstance[d.instanceID] or {}
	table.insert(byInstance[d.instanceID], d)
end

local function indexOf(floor)
	for i, f in ipairs(floors) do
		if f == floor then return i end
	end
end

local function roomOnFloor(room, floor)
	for _, box in ipairs(room.boxes) do
		if box[1] == floor then return true end
	end
	return false
end

-- The floor that shows most of the room.
local function roomMainFloor(room)
	local area, best, bestArea = {}, nil, nil
	for _, box in ipairs(room.boxes) do
		area[box[1]] = (area[box[1]] or 0) + box[4] * box[5]
	end
	for floor, a in pairs(area) do
		if not bestArea or a > bestArea or (a == bestArea and floor < best) then best, bestArea = floor, a end
	end
	return best
end

-- Middle of the room on a floor (weighted by the size of its parts), map coordinates 0..1.
local function roomCenter(room, floor)
	local su, sv, sum = 0, 0, 0
	for _, box in ipairs(room.boxes) do
		if box[1] == floor then
			local a = box[4] * box[5]
			su, sv, sum = su + box[2] * a, sv + box[3] * a, sum + a
		end
	end
	if sum == 0 then return nil end
	return su / sum, sv / sum
end

local function roomNamed(key, name)
	if type(name) ~= "string" or name == "" then return nil end
	for _, room in ipairs(ns.Rooms[key] or {}) do
		if room.name == name then return room end
	end
end

-- The name the game gives where you stand (the sub-zone, else the minimap's zone text).
local function subzone()
	local s = plain(GetSubZoneText())
	if type(s) ~= "string" or s == "" then s = plain(GetMinimapZoneText()) end
	return type(s) == "string" and s or nil
end

-- The approach is outdoors/uninstanced, even though its minimap is a cave.
-- A separate native context prevents its artwork/marks from entering floor 279.
local function findApproach()
	local inside = plain((IsInInstance()))
	if inside ~= false or not ns.WailingApproach then return nil end
	local here = subzone()
	if here == "Cavern of Mists" or here == "Wailing Caverns" then return ns.WailingApproach end
end

local function inMappedArea()
	return inDungeon() or findApproach() ~= nil
end

---------------------------------------------------------------------------------------------------
-- Which dungeon
---------------------------------------------------------------------------------------------------

-- The dungeon you are in. Instances with several wings (Scarlet Monastery, Blackrock Spire): the wing
-- whose room you stand in, else the one whose floor the game names, else the last pick, else the first.
local function findDungeon()
	if not inDungeon() then return findApproach() end
	local id = instanceID()
	local list = id and byInstance[id]
	if not list then return nil end
	if #list == 1 then return list[1] end
	local here = subzone()
	for _, d in ipairs(list) do
		if roomNamed(d.key, here) then wingPick[id] = d.key return d end
	end
	local best = plain(call(C_Map.GetBestMapForUnit, "player"))
	for _, d in ipairs(list) do
		for _, f in ipairs(d.floors) do
			if f == best then wingPick[id] = d.key return d end
		end
	end
	return byKey[wingPick[id] or ""] or list[1]
end

---------------------------------------------------------------------------------------------------
-- Boss kills (per character, per run)
---------------------------------------------------------------------------------------------------

local function clearInstanceRun(id)
	if not DungeonMapsCharDB.runs then return end
	-- Several wings can share one instance; none should retain the previous visit's kills.
	for _, d in ipairs(byInstance[id] or {}) do DungeonMapsCharDB.runs[d.key] = nil end
end

local function checkRunEntry(initialLogin, reloadingUI)
	local id = inDungeon() and instanceID() or nil
	if id and id ~= worldInstance and not plain(initialLogin) and not plain(reloadingUI)
		and not enteringDead and not plain(UnitIsDeadOrGhost("player")) then
		clearInstanceRun(id)
	end
	worldInstance = id
	enteringDead = false
end

local function run(key, create)
	DungeonMapsCharDB.runs = DungeonMapsCharDB.runs or {}
	local r = DungeonMapsCharDB.runs[key]
	if r and time() - (r.t or 0) > RUN_MAX_AGE then r = nil end
	if not r and create then
		r = { t = time(), killed = {} }
	end
	DungeonMapsCharDB.runs[key] = r
	return r
end

local function bossDone(key, index)
	local r = run(key, false)
	return r ~= nil and r.killed[index] == true
end

-- The boss of a dungeon an encounter belongs to: index, boss.
local function bossLabel(boss)
	local id = boss.encounters and boss.encounters[1]
	local locale = GetLocale and GetLocale() or "enUS"
	return (id and DungeonMapsDB.bossNames and DungeonMapsDB.bossNames[locale .. ":" .. id]) or boss.name
end

local function bossFor(key, encounterID, encounterName)
	for i, b in ipairs(ns.Bosses[key] or {}) do
		if type(encounterName) == "string" and (b.name == encounterName or bossLabel(b) == encounterName) then return i, b end
		for _, alias in ipairs(b.aliases or {}) do
			if alias == encounterName then return i, b end
		end
	end
	for i, b in ipairs(ns.Bosses[key] or {}) do
		for _, id in ipairs(b.encounters or {}) do
			if id == encounterID then return i, b end
		end
	end
end

local function learnBossLabel()
	-- Prefer the client's actual boss-unit name when one encounter identifies
	-- exactly one map pin and exactly one boss unit. Multi-boss events keep their
	-- curated individual names. No target/add names or fuzzy matching are used.
	local a = activeEncounter
	if not a then return end
	local count, boss = 0, nil
	for _, b in ipairs(ns.Bosses[a.key] or {}) do
		for _, id in ipairs(b.encounters or {}) do
			if id == a.id then count = count + 1; boss = b; break end
		end
	end
	if count ~= 1 then return end
	local name, units = nil, 0
	for i = 1, 8 do
		local n = plain(UnitName("boss" .. i))
		if type(n) == "string" and n ~= "" then units = units + 1; name = n end
	end
	if units ~= 1 then return end
	local locale = GetLocale and GetLocale() or "enUS"
	DungeonMapsDB.bossNames = DungeonMapsDB.bossNames or {}
	DungeonMapsDB.bossNames[locale .. ":" .. boss.encounters[1]] = name
end

local function onBossKilled(encounterID, encounterName)
	encounterID, encounterName = plain(encounterID), plain(encounterName)
	local d = findDungeon()
	if not d then return end
	local i = bossFor(d.key, encounterID, encounterName)
	if i then
		local r = run(d.key, true)
		r.killed[i] = true
		r.t = time()
	end
end

---------------------------------------------------------------------------------------------------
-- Landmarks: the moments the game shows where you are
---------------------------------------------------------------------------------------------------

local LM_ENTRANCE, LM_BOSS, LM_MARKED = 1, 2, 3

local function setLandmark(key, floor, u, v, label, kind)
	landmark = { key = key, floor = floor, u = u, v = v, label = label, t = GetTime(), kind = kind }
	landmarkCount = landmarkCount + 1
end

local function landmarkEntrance()
	local d = findDungeon()
	local e = d and ns.Entry[d.key]
	if e and #(byInstance[d.instanceID] or {}) == 1 then -- several wings: which door is unknown
		setLandmark(d.key, e.floor, e.x, e.y, "the entrance", LM_ENTRANCE)
	end
end

local function landmarkBoss(encounterID, encounterName)
	encounterID, encounterName = plain(encounterID), plain(encounterName)
	local d = findDungeon()
	if not d then return end
	local i, b = bossFor(d.key, encounterID, encounterName)
	-- A living boss that we marked dead is direct evidence of a fresh run, even
	-- if we logged in after zoning or missed the server's reset announcement.
	if i and bossDone(d.key, i) then clearInstanceRun(d.instanceID) end
	activeEncounter = b and { key = d.key, index = i, id = encounterID } or nil
	if b then setLandmark(d.key, b.floor, b.x, b.y, b.name, LM_BOSS) end
end

---------------------------------------------------------------------------------------------------
-- Group messages: rooms of teammates (same format as Forever Dungeon Routes)
--   P <key> <room> [L]   I am in this dungeon, in this room (English name; empty: none);
--                        L: my live tracker mode is on (the Dungeons Maps tracker draws me exactly,
--                        so the others don't draw a rough room dot for me; FDR ignores the extra field)
--   W                where are you? (answered with P)
---------------------------------------------------------------------------------------------------

local lastState, lastStateTime, stateTimer = nil, 0, false

local function channel()
	if LE_PARTY_CATEGORY_INSTANCE and plain(IsInGroup(LE_PARTY_CATEGORY_INSTANCE)) then return "INSTANCE_CHAT" end
	if plain(IsInRaid()) then return "RAID" end
	if plain(IsInGroup()) then return "PARTY" end
end

local function send(text)
	local ch = channel()
	if ch and C_ChatInfo and C_ChatInfo.SendAddonMessage then
		call(C_ChatInfo.SendAddonMessage, PREFIX, text, ch)
	end
end

local function myState()
	if not inDungeon() then return "P\t\t" end
	local d = findDungeon()
	if not d then return "P\t\t" end
	local room = roomNamed(d.key, subzone())
	return "P\t" .. d.key .. "\t" .. (room and room.name or "") .. (DungeonMapsDB.live ~= false and "\tL" or "")
end

local function sendState(force)
	if not channel() then
		lastState = nil
		return
	end
	local state = myState()
	if not force and state == lastState then return end
	local wait = STATE_GAP - (time() - lastStateTime)
	if not force and wait > 0 then
		if not stateTimer then
			stateTimer = true
			C_Timer.After(wait, function()
				stateTimer = false
				sendState()
			end)
		end
		return
	end
	lastState, lastStateTime = state, time()
	send(state)
end

local function onAddonMessage(prefix, text, sender)
	prefix, text, sender = plain(prefix), plain(text), plain(sender)
	if prefix ~= PREFIX or type(text) ~= "string" or type(sender) ~= "string" then return end
	if shortName(sender) == shortName(plain(UnitName("player"))) then return end
	local f = {}
	for field in (text .. "\t"):gmatch("([^\t]*)\t") do f[#f + 1] = field end
	if f[1] == "P" then
		if f[2] and byKey[f[2]] then
			members[sender] = { key = f[2], room = f[3] ~= "" and f[3] or nil, live = f[4] == "L" }
		else
			members[sender] = nil
		end
	elseif f[1] == "W" then
		sendState(true)
	end
end

-- Teammates' rooms in this dungeon: [short name] = room or false (no named room right now), and
-- which of them are in live mode (their exact spot comes from the tracker, not from here).
local function groupRooms()
	local out, live = {}, {}
	if not dungeon then return out, live end
	for sender, m in pairs(members) do
		if m.key == dungeon.key then
			local n = shortName(sender)
			if n then
				out[n] = roomNamed(dungeon.key, m.room) or false
				live[n] = m.live or nil
			end
		end
	end
	return out, live
end

---------------------------------------------------------------------------------------------------
-- Where everyone is
---------------------------------------------------------------------------------------------------

-- Remembers each person's named room; returns the room, whether it is current, and since when.
local function roomFor(name, current)
	local last = lastRoom[name]
	if current then
		-- a new sighting when the room changes or is walked into again
		if not (last and last.room == current and last.key == dungeon.key and last.now) then
			last = { room = current, key = dungeon.key, t = GetTime() }
			lastRoom[name] = last
		end
		last.now = true
		return current, true, last.t
	end
	if last then last.now = false end
	if last and last.key == dungeon.key then return last.room, false, last.t end
	return nil, false, nil
end

local function roomPoint(room, floor)
	if not room then return nil end
	if floor and roomOnFloor(room, floor) then
		local u, v = roomCenter(room, floor)
		if u then return floor, u, v end
	end
	local main = roomMainFloor(room)
	if main then
		local u, v = roomCenter(room, main)
		if u then return main, u, v end
	end
end

-- Your spot: the newest of the landmark and the named room.
local function mySpot(name, shownFloor)
	local room, now, since = roomFor(name, roomNamed(dungeon.key, subzone()))
	local lm = landmark and landmark.key == dungeon.key and landmark or nil
	if lm and (not room or (since or 0) <= lm.t) then
		return { floor = lm.floor, u = lm.u, v = lm.v, place = lm.label, how = "landmark",
			fresh = GetTime() - lm.t <= FRESH }
	end
	if room then
		local floor, u, v = roomPoint(room, shownFloor)
		if floor then
			return { floor = floor, u = u, v = v, place = room.name, how = now and "room" or "lastroom",
				fresh = now, room = room }
		end
	end
end

local function locatePeople()
	local people = {}
	local shown = floorIndex and floors[floorIndex]
	local me = shortName(plain(UnitName("player"))) or "You"
	local mine = mySpot(me, shown)
	people[1] = { name = me, unit = "player", r = 1, g = 0.82, b = 0.3, me = true, spot = mine,
		how = mine and mine.how or "unknown", place = mine and mine.place, fresh = mine and mine.fresh,
		room = mine and mine.room }
	local rooms, live = groupRooms()
	for _, unit in ipairs(groupUnits()) do
		local name = UnitExists(unit) and not plain(UnitIsUnit(unit, "player")) and (shortName(plain(UnitName(unit))) or "?")
		-- teammates without Dungeon Maps (they never sent a group message) only when the setting says
		if name and (rooms[name] ~= nil or DungeonMapsDB.showOthers == true) then
			local r, g, b = classColor(unit)
			local p = { name = name, unit = unit, r = r, g = g, b = b }
			local room, now = roomFor(name, rooms[name] or nil)
			local dead = plain(UnitIsDeadOrGhost(unit))
			local online = plain(UnitIsConnected(unit))
			p.status = online == false and "offline" or dead and "dead" or nil
			local near28 = plain(call(CheckInteractDistance, unit, 4))
			local near40 = plain(call(UnitInRange, unit))
			if live[name] and DungeonMapsDB.live ~= false then
				-- live on the tracker: the tracker's overlay draws them exactly (no second, rough dot)
				p.how, p.place, p.fresh = "live", room and room.name, true
			elseif room and now then
				local floor, u, v = roomPoint(room, shown)
				if floor then p.spot = { floor = floor, u = u, v = v } end
				p.how, p.place, p.fresh = "room", room.name, true
			elseif near28 == true and mine then
				p.spot, p.how, p.place, p.fresh = mine, "near28", "near you", mine.fresh
			elseif near40 == true and mine then
				p.spot, p.how, p.place, p.fresh = mine, "near40", "near you", false
			elseif room then
				local floor, u, v = roomPoint(room, shown)
				if floor then p.spot = { floor = floor, u = u, v = v } end
				p.how, p.place, p.fresh = "lastroom", room.name, false
			else
				p.how = "unknown"
			end
			people[#people + 1] = p
		end
	end
	return people
end

---------------------------------------------------------------------------------------------------
-- Drawing: room glow, bosses, dots with names
---------------------------------------------------------------------------------------------------

local function tooltipOn(frame)
	frame:EnableMouse(true)
	frame:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
		GameTooltip:SetText(self.tipTitle or "", self.tipR or 1, self.tipG or 0.82, self.tipB or 0)
		for _, line in ipairs(self.tipLines or {}) do GameTooltip:AddLine(line, 1, 1, 1, true) end
		GameTooltip:Show()
		if self.hover then self.hover:Show() end
	end)
	frame:SetScript("OnLeave", function(self)
		GameTooltip:Hide()
		if self.hover then self.hover:Hide() end
	end)
end

local function getDot(i)
	local d = map.dots[i]
	if d then return d end
	d = CreateFrame("Frame", nil, map.dotLayer)
	d:SetSize(DOT, DOT)
	d.ring = d:CreateTexture(nil, "ARTWORK", nil, 1)
	d.ring:SetAtlas(BLIP_ATLAS)
	d.ring:SetPoint("CENTER")
	d.blip = d:CreateTexture(nil, "ARTWORK", nil, 2)
	d.blip:SetAtlas(BLIP_ATLAS)
	d.blip:SetPoint("CENTER")
	d.label = d:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	d.label:SetFont(STANDARD_TEXT_FONT, 13, "OUTLINE")
	d.label:SetPoint("LEFT", d, "RIGHT", 3, 0)
	tooltipOn(d)
	map.dots[i] = d
	return d
end

local function getBoss(i)
	local b = map.bosses[i]
	if b then return b end
	b = CreateFrame("Frame", nil, map.bossLayer)
	b:SetSize(BOSS, BOSS)
	b.back = b:CreateTexture(nil, "ARTWORK", nil, 1)
	b.back:SetAtlas(BLIP_ATLAS)
	b.back:SetVertexColor(0, 0, 0, 0.85)
	b.back:SetSize(BOSS + 4, BOSS + 4)
	b.back:SetPoint("CENTER")
	b.icon = b:CreateTexture(nil, "ARTWORK", nil, 2)
	b.icon:SetTexture(SKULL)
	b.icon:SetSize(BOSS - 6, BOSS - 6)
	b.icon:SetPoint("CENTER")
	b.hover = b:CreateTexture(nil, "ARTWORK", nil, 3)
	b.hover:SetAtlas(BLIP_ATLAS)
	b.hover:SetVertexColor(1, 0.82, 0.3, 0.45)
	b.hover:SetBlendMode("ADD")
	b.hover:SetSize(BOSS + 14, BOSS + 14)
	b.hover:SetPoint("CENTER")
	b.hover:Hide()
	b.num = b:CreateFontString(nil, "OVERLAY")
	b.num:SetFont(STANDARD_TEXT_FONT, 12, "OUTLINE")
	b.num:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", 5, -3)
	tooltipOn(b)
	map.bosses[i] = b
	return b
end

local function drawBosses(floor)
	local n = 0
	for i, boss in ipairs(dungeon and ns.Bosses[dungeon.key] or {}) do
		if boss.floor == floor then
			n = n + 1
			local b = getBoss(n)
			local size = BOSS * sizeOf("bossSize")
			b:SetSize(size, size)
			b.back:SetSize(size + 4, size + 4)
			b.icon:SetSize(size - 6, size - 6)
			b.hover:SetSize(size + 14, size + 14)
			b.num:SetFont(STANDARD_TEXT_FONT, math.floor(12 * math.max(1, sizeOf("bossSize") * 0.8) + 0.5), "OUTLINE")
			local done = bossDone(dungeon.key, i)
			b:ClearAllPoints()
			b:SetPoint("CENTER", map.canvas, "TOPLEFT", boss.x * MAP_W, -boss.y * MAP_H)
			b.num:SetText(tostring(i))
			b.icon:SetDesaturated(done)
			b:SetAlpha(done and 0.6 or 1)
			b.tipTitle = bossLabel(boss)
			b.tipR, b.tipG, b.tipB = 1, 0.3, 0.3
			b.tipLines = { ("Boss %d"):format(i) .. (done and "  -  |cff88ff88defeated|r" or "") }
			if boss.encounterName and boss.encounterName ~= b.tipTitle then
				table.insert(b.tipLines, "Encounter: " .. boss.encounterName)
			end
			if boss.note and boss.note ~= "" then table.insert(b.tipLines, boss.note) end
			b:Show()
		end
	end
	for i = n + 1, #map.bosses do map.bosses[i]:Hide() end
end

local function drawGlow(room, floor)
	local n = 0
	if room then
		for _, box in ipairs(room.boxes) do
			if box[1] == floor then
				n = n + 1
				local t = map.glow[n]
				if not t then
					t = map.canvas:CreateTexture(nil, "BORDER")
					t:SetColorTexture(1, 0.82, 0.3)
					map.glow[n] = t
				end
				-- room boxes are turned by box[6]; nearly all by a multiple of 90 degrees, so the turned
				-- box is drawn as its upright bounding box (exact at 0/90/180/270 degrees)
				local c, s = math.abs(math.cos(box[6])), math.abs(math.sin(box[6]))
				t:SetSize(box[4] * c + box[5] * s, box[4] * s + box[5] * c)
				t:ClearAllPoints()
				t:SetPoint("CENTER", map.canvas, "TOPLEFT", box[2] * MAP_W, -box[3] * MAP_H)
				t:SetAlpha(0.16)
				t:Show()
			end
		end
	end
	for i = n + 1, #map.glow do map.glow[i]:Hide() end
end

local HOW_TEXT = {
	landmark = "seen at %s",
	room = "in %s",
	lastroom = "last seen in %s",
	near28 = "within ~28 yards of you",
	near40 = "within ~40 yards of you",
}

local function drawDots(people)
	local floor = floorIndex and floors[floorIndex]
	local groups, order = {}, {}
	for _, p in ipairs(people) do
		local s = p.spot
		if p.me and DungeonMapsDB.live ~= false and not dungeon.approach then s = nil end
		if s then
			if s.floor == floor then
				local key = ("%.4f:%.4f"):format(s.u, s.v)
				local g = groups[key]
				if not g then
					g = { u = s.u, v = s.v, list = {} }
					groups[key] = g
					order[#order + 1] = g
				end
				table.insert(g.list, p)
			else
				p.elsewhere = true
			end
		end
	end
	local n = 0
	for _, g in ipairs(order) do
		local cx, cy = g.u * MAP_W, g.v * MAP_H
		local others, hasMe = 0, false
		for _, p in ipairs(g.list) do
			if p.me then hasMe = true else others = others + 1 end
		end
		local k = 0
		for _, p in ipairs(g.list) do
			n = n + 1
			local d = getDot(n)
			local x, y = cx, cy
			if not p.me and (hasMe or others > 1) then
				-- teammates on a ring around the spot (around you when placed by range);
				-- one teammate alone on a spot sits on it
				k = k + 1
				local radius = ((p.how == "near28" or p.how == "near40") and NEAR_RING or SPREAD) * math.max(1, sizeOf("dotSize"))
				local angle = (k - 1) / math.max(others, 1) * 2 * math.pi - math.pi / 2
				x, y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
			end
			local size = (p.me and ME_DOT or DOT) * sizeOf("dotSize")
			d.label:SetFont(STANDARD_TEXT_FONT, math.floor(13 * math.max(0.85, math.min(1.6, sizeOf("dotSize"))) + 0.5), "OUTLINE")
			d:SetSize(size, size)
			d.blip:SetSize(size, size)
			d.ring:SetSize(size + 6, size + 6)
			if p.me then
				d.blip:SetVertexColor(1, 0.82, 0.3)
				d.ring:SetVertexColor(1, 1, 1)
			else
				d.blip:SetVertexColor(p.r, p.g, p.b)
				d.ring:SetVertexColor(0, 0, 0)
			end
			d:SetFrameLevel(map.dotLayer:GetFrameLevel() + (p.me and 5 or 2))
			d:ClearAllPoints()
			d:SetPoint("CENTER", map.canvas, "TOPLEFT", x, -y)
			d.label:SetText(p.me and "You" or p.name)
			d.label:SetTextColor(p.r, p.g, p.b)
			local alpha = p.fresh and 1 or OLD_FADE
			if p.how == "near40" then alpha = math.min(alpha, FAR_FADE) end
			if p.status then alpha = math.min(alpha, 0.5) end
			d:SetAlpha(alpha)
			d.tipTitle = p.me and (p.name .. " (you)") or p.name
			d.tipR, d.tipG, d.tipB = p.r, p.g, p.b
			d.tipLines = { (HOW_TEXT[p.how] or "%s"):format(p.place or "?") .. (p.status and (" (" .. p.status .. ")") or "") }
			d:Show()
		end
	end
	for i = n + 1, #map.dots do map.dots[i]:Hide() end
end

---------------------------------------------------------------------------------------------------
-- Legend
---------------------------------------------------------------------------------------------------

local function legendDetail(p)
	if p.status then return p.status end
	if p.me and dungeon.approach then return "Approach cave: A = cave entrance; B = instance portal" end
	if p.me and DungeonMapsDB.live ~= false then
		if landmark and landmark.kind == LM_MARKED and GetTime() - landmark.t < 5 then return "marked - the arrow starts here" end
		return "live arrow (Shift+click the map where you stand to set it)"
	end
	if p.how == "unknown" then return p.me and "not placed yet" or "far away" end
	if p.how == "live" then return "live on the tracker" .. (p.place and (", " .. p.place) or "") end
	local text = p.place or "?"
	if p.how == "landmark" then text = (p.fresh and "at " or "last seen at ") .. text end
	if p.how == "lastroom" then text = "last: " .. text end
	if p.elsewhere then text = text .. ", other floor" end
	return text
end

local function refreshLegend(people)
	local legend = map.legend
	local shown = math.min(#people, LEGEND_MAX)
	local width = 60
	for i = 1, LEGEND_MAX + 1 do
		local line = legend.lines[i]
		if not line then
			line = {}
			line.dot = legend:CreateTexture(nil, "OVERLAY")
			line.dot:SetSize(12, 12)
			line.dot:SetAtlas(BLIP_ATLAS)
			line.dot:SetPoint("TOPLEFT", 8, -6 - (i - 1) * LEGEND_ROW - 2)
			line.text = legend:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
			line.text:SetPoint("LEFT", line.dot, "RIGHT", 6, 0)
			legend.lines[i] = line
		end
		local p = people[i]
		if i <= shown then
			line.dot:SetVertexColor(p.r, p.g, p.b)
			local hex = ("|cff%02x%02x%02x"):format(p.r * 255, p.g * 255, p.b * 255)
			line.text:SetText(hex .. (p.me and (p.name .. " (you)") or p.name) .. "|r  |cffb0b0b0" .. legendDetail(p) .. "|r")
			line.dot:Show()
			line.text:Show()
		elseif i == shown + 1 and #people > shown then
			line.dot:Hide()
			line.text:SetText(("|cffccccccand %d more|r"):format(#people - shown))
			line.text:Show()
		else
			line.dot:Hide()
			line.text:Hide()
		end
		if line.text:IsShown() then width = math.max(width, line.text:GetStringWidth() + 34) end
	end
	legend:SetSize(width, (shown + (#people > shown and 1 or 0)) * LEGEND_ROW + 12)
end

local function refreshPeople()
	if not (map and map:IsShown() and dungeon) then return end
	local people = locatePeople()
	local floor = floorIndex and floors[floorIndex]
	drawGlow(people[1].how == "room" and people[1].room or nil, floor)
	drawBosses(floor)
	drawDots(people)
	refreshLegend(people)
end

---------------------------------------------------------------------------------------------------
-- Diagnostics (saved, read later from WTF)
---------------------------------------------------------------------------------------------------

local function recordDiag()
	local best = C_Map and plain(call(C_Map.GetBestMapForUnit, "player"))
	local ux, uy, _, uinst = call(UnitPosition, "player")
	ux, uy = plain(ux), plain(uy)
	local version, build = GetBuildInfo()
	local room = dungeon and roomNamed(dungeon.key, subzone())
	local d = {
		time = date("%Y-%m-%d %H:%M"),
		build = tostring(version) .. "." .. tostring(build),
		instanceID = instanceID(),
		instanceName = plain((GetInstanceInfo())),
		dungeonKey = dungeon and dungeon.key,
		subzone = subzone(),
		room = room and room.name or "none",
		landmark = landmark and ("%s %.0fs ago"):format(tostring(landmark.label), GetTime() - landmark.t) or "none",
		bestMap = best,
		shownFloor = floorIndex and floors[floorIndex],
		unitPosition = (type(ux) == "number" and type(uy) == "number") and ("%.1f, %.1f"):format(ux, uy) or "none",
		unitPositionInstance = plain(uinst),
		facing = plain(call(GetPlayerFacing)),
		group = {},
	}
	for _, unit in ipairs(groupUnits()) do
		if UnitExists(unit) then
			d.group[#d.group + 1] = ("%s near28=%s near40=%s"):format(tostring(plain(UnitName(unit))),
				tostring(plain(call(CheckInteractDistance, unit, 4))), tostring(plain(call(UnitInRange, unit))))
		end
	end
	for name, r in pairs(groupRooms()) do
		d.group[#d.group + 1] = ("%s shared room=%s"):format(name, r and r.name or "none")
	end
	DungeonMapsDB.diag = DungeonMapsDB.diag or {}
	DungeonMapsDB.diag[tostring(d.instanceID or "?") .. ":" .. tostring(d.shownFloor or "?")] = d
	DungeonMapsDB.lastDiag = d
	return d
end

---------------------------------------------------------------------------------------------------
-- The map window
---------------------------------------------------------------------------------------------------

local function showFloor(index)
	if not floors[index] then return end
	floorIndex = index
	local floor = floors[index]
	local info = ns.Floors[floor]
	local image = info and info.image
	local missing = false
	if image then
		local file = image.routeFile and DungeonMapsDB.wailingRoute ~= false and image.routeFile or image.file
		missing = map.picture:SetTexture(ADDON_PATH .. file, nil, nil, "TRILINEAR") == false
		if missing then image = nil end
	end
	local terrain = not image and info and info.terrain and ns.MinimapArt[floor]
	local tiles = not image and not terrain and not missing and info and info.tiles
	for i, tex in ipairs(map.tiles) do
		if tiles then
			tex:SetTexture(tiles[i], nil, nil, "TRILINEAR") -- the game's own map tile (file ID)
			tex:Show()
		else
			tex:Hide()
		end
	end
	-- Santiago Reyes's pictures are bundled with the addon; no other addon or discovery API needed.
	if image then
		map.picture:ClearAllPoints()
		if image.square then
			map.picture:SetSize(MAP_H, MAP_H)
			map.picture:SetPoint("TOP", map.canvas, "TOP", 0, 0)
		else
			map.picture:SetAllPoints(map.canvas)
		end
		map.picture:SetTexCoord(0, image.right or 1, 0, image.bottom or 1)
		map.picture:Show()
	else
		map.picture:Hide()
	end
	-- Wailing Caverns' parchment leaves out an entire wing. These client
	-- textures use the same 1002x668 coordinates as its bosses and live arrow.
	-- Set up only on floor changes; no per-frame texture work.
	local count = terrain and #terrain or 0
	map.terrainBack:SetShown(count > 0)
	for i = 1, count do
		local part, tex = terrain[i], map.terrainTiles[i]
		if not tex then
			tex = map.canvas:CreateTexture(nil, "BACKGROUND")
			map.terrainTiles[i] = tex
		end
		tex:SetTexture(part[1], "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE", "TRILINEAR")
		tex:SetTexCoord(part[6], part[7], part[8], part[9], part[10], part[11], part[12], part[13])
		tex:SetDrawLayer("BACKGROUND", part[14])
		tex:SetSize(part[4], part[5])
		tex:ClearAllPoints()
		tex:SetPoint("TOPLEFT", map.canvas, "TOPLEFT", part[2], -part[3])
		tex:Show()
	end
	for i = count + 1, #map.terrainTiles do map.terrainTiles[i]:Hide() end
	map.noArt:SetText(missing and "New map: fully restart WoW once to load its pictures" or "No map art for this floor")
	map.noArt:SetShown(not tiles and not image and count == 0)
	map.credit:SetText(missing and "New clean map: fully restart WoW once to load it" or (info and info.credit or ""))
	map.portal:SetShown(dungeon.approach == true and image ~= nil)
	if dungeon.approach then
		map.note:SetText("|cffffd100APPROACH CAVE: A = cave entrance; B = instance portal.|r  The dungeon map starts after the portal.")
	elseif dungeon.key == "wailingcaverns" then
		if DungeonMapsDB.wailingRoute ~= false then
			map.note:SetText("|cffffd100INSTANCE ONLY.|r  Teal: boss circuit. Gold: Naralex escort. Crossings may be on different levels. Hide guide in gear menu.")
		else
			map.note:SetText("|cffffd100INSTANCE ONLY.|r  Shift+click where you stand. Enable the route guide in the gear menu for the boss circuit.")
		end
	else
		map.note:SetText("|cffffd100Shift+click where you stand to place your arrow.|r   Skulls: bosses.   Dots: where the game last showed someone.")
	end
	local wings = #(byInstance[dungeon.instanceID] or {})
	map.title:SetText(dungeon.name .. (wings > 1 and "  |cff999999(click: other wing)|r" or ""))
	local name = info and info.name or ("Map " .. tostring(floor))
	map.floorText:SetText(#floors > 1 and ("%s  (%d/%d)"):format(name, index, #floors) or name)
	map.prev:SetEnabled(index > 1)
	map.next:SetEnabled(index < #floors)
	map.prev:SetShown(#floors > 1)
	map.next:SetShown(#floors > 1)
	refreshPeople()
end

local function step(delta)
	if floorIndex then
		manualAt = GetTime()
		showFloor(math.max(1, math.min(#floors, floorIndex + delta)))
	end
end

-- The floor of the next boss not killed yet.
local function nextBossFloor()
	for i, b in ipairs(ns.Bosses[dungeon.key] or {}) do
		if not bossDone(dungeon.key, i) and indexOf(b.floor) then return b.floor end
	end
end

-- The floor to follow: your spot's floor, else the game's map, else the next boss's floor.
local function wantedFloor()
	local me = shortName(plain(UnitName("player"))) or "You"
	local spot = mySpot(me, floorIndex and floors[floorIndex])
	if spot and indexOf(spot.floor) then return spot.floor end
	local best = plain(call(C_Map.GetBestMapForUnit, "player"))
	if type(best) == "number" and indexOf(best) then return best end
	return nextBossFloor()
end

local function makeArrowButton(parent, left)
	local b = CreateFrame("Button", nil, parent)
	b:SetSize(26, 26)
	local dir = left and "Prev" or "Next"
	b:SetNormalTexture("Interface\\Buttons\\UI-SpellbookIcon-" .. dir .. "Page-Up")
	b:SetPushedTexture("Interface\\Buttons\\UI-SpellbookIcon-" .. dir .. "Page-Down")
	b:SetDisabledTexture("Interface\\Buttons\\UI-SpellbookIcon-" .. dir .. "Page-Disabled")
	b:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
	b:SetScript("OnClick", function() step(left and -1 or 1) end)
	return b
end

local function setDungeon(d)
	dungeon = d
	floors = d.floors or {}
	manualAt = 0
	showFloor(indexOf(wantedFloor() or floors[1]) or 1)
end

-- Several wings in one instance: the title cycles through them.
local function nextWing()
	local list = dungeon and byInstance[dungeon.instanceID]
	if not list or #list < 2 then return end
	for i, d in ipairs(list) do
		if d == dungeon then
			local nd = list[i % #list + 1]
			wingPick[dungeon.instanceID] = nd.key
			setDungeon(nd)
			return
		end
	end
end

-- Blizzard's world map, opened or closed from add-on code only out of combat. (Add-on code touching
-- the world map -- above all WorldMapFrame:SetMapID -- taints it, and WoW then blocks the map's own
-- protected updates in combat: "Interface actions failed because of this AddOn".)
local function toggleWorldMap()
	if InCombatLockdown() then
		say("the world map can't be switched from here in combat; it works again after the fight.")
		return false
	end
	ToggleWorldMap()
	return true
end

-- The normal world map (Blizzard's map picks the zone itself; "Dungeon Map" on it brings you back).
local function openWorldMap()
	if WorldMapFrame and WorldMapFrame:IsShown() then
		if map then map:Hide() end
		return
	end
	if toggleWorldMap() and map then map:Hide() end
end

local openMap -- (below)

-- "Dungeon Map" on Blizzard's world map, shown while you are in a dungeon.
local function buildBackButton()
	if backButton or not WorldMapFrame then return end
	backButton = CreateFrame("Button", "DungeonMapsBackButton", WorldMapFrame, "UIPanelButtonTemplate")
	backButton:SetSize(130, 24)
	backButton:SetText("Dungeon Map")
	backButton:SetPoint("BOTTOMLEFT", WorldMapFrame, "BOTTOMLEFT", 16, 16)
	backButton:SetFrameStrata("FULLSCREEN_DIALOG")
	backButton:SetScript("OnClick", function()
		if WorldMapFrame:IsShown() then toggleWorldMap() end
		openMap()
	end)
	local function sync() backButton:SetShown(inMappedArea() and findDungeon() ~= nil) end
	WorldMapFrame:HookScript("OnShow", sync)
	sync()
end

-- Forever Dungeon Routes, if it is still installed, opens its small map on entering a dungeon; Brett
-- doesn't want that. Its setting "on entering a dungeon" goes to "none" and an open small map closes.
local function quietRoutes()
	local dr = _G.ForeverDungeonRoutes
	if not (dr and dr.db) then return end
	dr.db.onEnter = "none"
	dr.hinted = true
	if dr.Window and call(dr.Window.IsMini, dr.Window) then call(dr.Window.CloseMini, dr.Window) end
end

local function buildMap()
	map = CreateFrame("Frame", "DungeonMapsFrame", UIParent, "BackdropTemplate")
	map:SetSize(MAP_W + PAD * 2, MAP_H + BAR_H + PAD * 2)
	map:SetPoint("CENTER")
	map:SetFrameStrata("HIGH")
	map:SetToplevel(true)
	map:SetClampedToScreen(true)
	map:SetMovable(true)
	map:EnableMouse(true)
	map:RegisterForDrag("LeftButton")
	map:SetScript("OnDragStart", function(self) if not IsShiftKeyDown() then self:StartMoving() end end)
	map:SetScript("OnDragStop", map.StopMovingOrSizing)
	-- Shift+click on the map: "I am here" (starts or corrects the live arrow, and your landmark dot)
	map:SetScript("OnMouseUp", function(_, button)
		if button ~= "LeftButton" or not IsShiftKeyDown() or not (dungeon and floorIndex) then return end
		local c = map.canvas
		local x, y = GetCursorPosition()
		local s = c:GetEffectiveScale()
		local u = (x / s - c:GetLeft()) / c:GetWidth()
		local v = (c:GetTop() - y / s) / c:GetHeight()
		if u < 0 or u > 1 or v < 0 or v > 1 then return end
		setLandmark(dungeon.key, floors[floorIndex], u, v, "where you marked", LM_MARKED)
		refreshPeople()
	end)
	map:SetBackdrop({
		bgFile = "Interface\\ChatFrame\\ChatFrameBackground",
		edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Gold-Border",
		edgeSize = 24,
		insets = { left = 5, right = 5, top = 5, bottom = 5 },
	})
	map:SetBackdropColor(0.06, 0.05, 0.04, 0.96)
	map:Hide()
	tinsert(UISpecialFrames, "DungeonMapsFrame") -- Esc closes it, like the world map

	local function fit()
		local s = math.min(1, UIParent:GetHeight() * 0.85 / map:GetHeight(), UIParent:GetWidth() * 0.92 / map:GetWidth())
		map:SetScale(s)
	end
	fit()
	map:RegisterEvent("UI_SCALE_CHANGED")
	map:RegisterEvent("DISPLAY_SIZE_CHANGED")
	map:SetScript("OnEvent", fit)

	-- top bar: [World Map] Dungeon name ........ < Floor > ........ [x]
	local world = CreateFrame("Button", nil, map, "UIPanelButtonTemplate")
	world:SetSize(104, 22)
	world:SetText("World Map")
	world:SetPoint("TOPLEFT", PAD + 6, -PAD - 4)
	world:SetScript("OnClick", openWorldMap)
	world:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_BOTTOMRIGHT")
		GameTooltip:SetText("World Map")
		GameTooltip:AddLine("Opens the normal world map. \"Dungeon Map\" on it brings you back. (Not in combat.)", 1, 1, 1, true)
		GameTooltip:Show()
	end)
	world:SetScript("OnLeave", function() GameTooltip:Hide() end)
	local titleButton = CreateFrame("Button", nil, map)
	titleButton:SetPoint("LEFT", world, "RIGHT", 10, 0)
	titleButton:SetSize(360, 22)
	titleButton:SetScript("OnClick", nextWing)
	map.title = titleButton:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
	map.title:SetPoint("LEFT")
	map.prev = makeArrowButton(map, true)
	map.next = makeArrowButton(map, false)
	map.floorText = map:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
	map.floorText:SetPoint("TOP", map, "TOP", 0, -PAD - 8)
	map.prev:SetPoint("RIGHT", map.floorText, "LEFT", -6, 0)
	map.next:SetPoint("LEFT", map.floorText, "RIGHT", 6, 0)
	local close = CreateFrame("Button", nil, map, "UIPanelCloseButton")
	close:SetPoint("TOPRIGHT", -2, -2)
	map.closeButton = close

	-- the canvas: 1002 x 668, the top-left of a 4 x 3 grid of 256-px tiles (Blizzard's map layout)
	local canvas = CreateFrame("Frame", nil, map)
	canvas:SetSize(MAP_W, MAP_H)
	canvas:SetPoint("TOPLEFT", PAD, -(PAD + BAR_H))
	canvas:SetClipsChildren(true)
	map.canvas = canvas
	if ns.makeGear then ns.makeGear(map) end
	map.tiles = {}
	for row = 0, 2 do
		for col = 0, 3 do
			local t = canvas:CreateTexture(nil, "BACKGROUND")
			t:SetSize(TILE, TILE)
			t:SetPoint("TOPLEFT", col * TILE, -row * TILE)
			map.tiles[#map.tiles + 1] = t
		end
	end
	map.picture = canvas:CreateTexture(nil, "BACKGROUND", nil, 1)
	map.picture:SetAllPoints(canvas)
	map.terrainBack = canvas:CreateTexture(nil, "BACKGROUND", nil, -1)
	map.terrainBack:SetAllPoints(canvas)
	map.terrainBack:SetColorTexture(0.035, 0.035, 0.025, 1)
	map.terrainBack:Hide()
	map.terrainTiles = {}
	map.noArt = canvas:CreateFontString(nil, "OVERLAY", "GameFontDisableLarge")
	map.noArt:SetPoint("CENTER")
	map.noArt:SetText("No map art for this floor")
	map.glow = {}

	map.bossLayer = CreateFrame("Frame", nil, canvas)
	map.bossLayer:SetAllPoints(canvas)
	map.bossLayer:SetFrameLevel(canvas:GetFrameLevel() + 5)
	map.bosses = {}

	map.dotLayer = CreateFrame("Frame", nil, canvas)
	map.dotLayer:SetAllPoints(canvas)
	map.dotLayer:SetFrameLevel(canvas:GetFrameLevel() + 10)
	map.dots = {}

	local legend = CreateFrame("Frame", nil, canvas, "BackdropTemplate")
	legend:SetPoint("BOTTOMLEFT", 10, 10)
	legend:SetFrameLevel(canvas:GetFrameLevel() + 30)
	legend:SetBackdrop({
		bgFile = "Interface\\ChatFrame\\ChatFrameBackground",
		edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
		edgeSize = 12,
		insets = { left = 3, right = 3, top = 3, bottom = 3 },
	})
	legend:SetBackdropColor(0, 0, 0, 0.7)
	legend:SetBackdropBorderColor(0.6, 0.5, 0.3, 0.9)
	legend.lines = {}
	map.legend = legend

	local note = canvas:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	map.note = note
	note:SetPoint("BOTTOMRIGHT", -10, 8)
	note:SetText("|cffffd100Shift+click where you stand to place your arrow.|r   Skulls: bosses.   Dots: where the game last showed someone.")
	map.credit = canvas:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
	map.credit:SetPoint("BOTTOMRIGHT", note, "TOPRIGHT", 0, 3)
	map.portal = canvas:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
	map.portal:SetPoint("LEFT", canvas, "TOPLEFT", (MAP_W-MAP_H)/2 + 270*MAP_H/512 + 10, -350*MAP_H/512)
	map.portal:SetText("B - INSTANCE PORTAL")
	map.portal:Hide()

	local elapsed = 0
	map:SetScript("OnUpdate", function(_, dt)
		elapsed = elapsed + dt
		if elapsed < POLL then return end
		elapsed = 0
		-- walking into a room of another wing (Scarlet Monastery, Blackrock Spire) switches the map
		local d = findDungeon()
		if not d then map:Hide(); return end
		if d and d ~= dungeon then
			setDungeon(d)
			return
		end
		if GetTime() - manualAt > MANUAL_HOLD then
			local want = wantedFloor()
			local i = want and indexOf(want)
			if i and i ~= floorIndex then
				showFloor(i)
				return
			end
		end
		refreshPeople()
	end)
end

openMap = function()
	local d = findDungeon()
	if not d then
		say("no map for this instance; opening the world map.")
		toggleWorldMap()
		return
	end
	if WorldMapFrame and WorldMapFrame:IsShown() and not InCombatLockdown() then ToggleWorldMap() end
	if not map then buildMap() end
	map:Show()
	setDungeon(d)
	recordDiag()
end

---------------------------------------------------------------------------------------------------
-- Live beacon: a 52 x 2 pixel strip of 26 coloured cells in the top-left corner of the game that the
-- screen tracker (a separate
-- Linux program, ~/Projects/wow-dungeon-tracker) reads from the screen. It carries what only the game
-- knows: the dungeon, landmarks, the room, the minimap zoom, and where the minimap and the dungeon map
-- are on the screen (in pixels, from the strip). Nothing leaves the game any other way.
--   cells 1-2: magenta, green (to find the strip); 3-5: the 8 colour levels (calibration)
--   cells 6-26: 9 bits each (3 per colour channel), the fields below, then a checksum
---------------------------------------------------------------------------------------------------

local BEACON_CELLS, BEACON_PX = 58, 2 -- cells, physical pixels per cell side
local HEADER = { { 7, 0, 7 }, { 0, 7, 0 }, { 0, 1, 2 }, { 3, 4, 5 }, { 6, 7, 0 } }
local beacon

local dungeonIndex = {}
for i, d in ipairs(ns.Dungeons) do dungeonIndex[d] = i end

local function pushBits(bits, value, n)
	value = math.max(0, math.min(2 ^ n - 1, math.floor(value + 0.5)))
	for i = n - 1, 0, -1 do bits[#bits + 1] = math.floor(value / 2 ^ i) % 2 end
end

-- Physical pixels per UI unit of a frame, and its top-left corner in physical pixels (from the top).
local function pixelRect(frame)
	local _, physH = GetPhysicalScreenSize()
	local k = physH / (UIParent:GetHeight() * UIParent:GetEffectiveScale())
	local s = frame:GetEffectiveScale() * k
	local left, top = frame:GetLeft(), frame:GetTop()
	if not (left and top) then return nil end
	return left * s, physH - top * s, frame:GetWidth() * s, frame:GetHeight() * s
end

-- UI geometry is more reliable than trying to recognize popup text in pixels.
local function coversMinimap(frame)
	if not frame or not frame:IsShown() then return false end
	local x, y, w, h = pixelRect(frame)
	local mx, my, mw, mh = pixelRect(Minimap)
	if not (x and mx) then return false end
	return math.min(x + w, mx + mw) - math.max(x, mx) > mw * 0.1
		and math.min(y + h, my + mh) - math.max(y, my) > mh * 0.1
end

-- Your live arrow's size on the map (Settings > AddOns > Dungeon Maps, or /dmaps size 1.5)
local ARROW_MIN, ARROW_MAX = 0.5, 2.5
local function arrowSize()
	return sizeOf("arrowSize")
end

-- The same number for everyone in the group: a hash of the members' GUIDs, sorted. 0 = not grouped.
local groupKeyValue, groupKeyAt = 0, -10
local function groupKey()
	local now = GetTime()
	if now - groupKeyAt < 1 then return groupKeyValue end
	groupKeyAt = now
	local ids = {}
	local function add(unit)
		local g = UnitGUID(unit)
		if g and not (issecretvalue and issecretvalue(g)) then ids[#ids + 1] = g end
	end
	if IsInRaid() then
		for i = 1, GetNumGroupMembers() do add("raid" .. i) end
	elseif IsInGroup() then
		add("player")
		for i = 1, 4 do add("party" .. i) end
	end
	local h = 0
	if #ids >= 2 then
		table.sort(ids)
		local s = table.concat(ids, ",")
		h = 5381
		for i = 1, #s do h = (h * 33 + s:byte(i)) % 4294967296 end -- djb2, kept exact in doubles
		if h == 0 then h = 1 end
	end
	groupKeyValue = h
	return h
end

-- (reused on every update: the beacon is redrawn ~33 times a second, so fresh tables would churn
-- hundreds of KB of garbage a second)
local beaconBits, beaconOut = {}, {}

local function beaconCells()
	local d = inDungeon() and findDungeon() or nil
	local bits = beaconBits
	for i = #bits, 1, -1 do bits[i] = nil end
	local open = map and map:IsShown() and dungeon == d
	-- indoors: the minimap's zoom differs from the outdoor zoom setting (HereBeDragons' test)
	local zoom = plain(Minimap:GetZoom()) or 0
	local indoors = tonumber(GetCVar("minimapZoom")) ~= zoom
	local radius = C_Minimap and plain(call(C_Minimap.GetViewRadius)) -- yards from centre to edge
	pushBits(bits, 7, 3) -- format version
	pushBits(bits, open and 1 or 0, 1)
	pushBits(bits, indoors == true and 1 or indoors == false and 2 or 0, 2)
	pushBits(bits, GetCVar("rotateMinimap") == "1" and 1 or 0, 1)
	pushBits(bits, zoom, 3)
	pushBits(bits, type(radius) == "number" and radius * 4 or 0, 11)
	pushBits(bits, d and dungeonIndex[d] or 0, 6)
	pushBits(bits, open and floorIndex or 0, 4)
	local lm = d and landmark and landmark.key == d.key and landmark or nil
	local lmFloor = 0
	if lm then
		for i, f in ipairs(d.floors) do if f == lm.floor then lmFloor = i end end
	end
	pushBits(bits, landmarkCount % 64, 6)
	pushBits(bits, lm and lm.kind or 0, 2)
	pushBits(bits, lmFloor, 4)
	pushBits(bits, lm and lm.u * 4095 or 0, 12)
	pushBits(bits, lm and lm.v * 4095 or 0, 12)
	local roomIndex = 0
	if d then
		local here = subzone()
		for i, room in ipairs(ns.Rooms[d.key] or {}) do
			if room.name == here then roomIndex = i break end
		end
	end
	pushBits(bits, roomIndex, 7)
	local bx, by = pixelRect(beacon)
	-- the minimap's rectangle, then the dungeon map canvas's (zeros when it isn't open)
	for k = 1, 2 do
		local frame = k == 1 and Minimap or (open and map and map.canvas) or nil
		local x, y, w, h
		if frame then x, y, w, h = pixelRect(frame) end
		if x and bx then
			pushBits(bits, x - bx + 4096, 13)
			pushBits(bits, y - by + 4096, 13)
			pushBits(bits, w, 12)
			pushBits(bits, h, 12)
		else
			for _ = 1, 50 do bits[#bits + 1] = 0 end
		end
	end
	-- v2: the party (so trackers in the same group find each other) and who you are (their labels)
	pushBits(bits, groupKey(), 32)
	local name = UnitName("player") or ""
	if issecretvalue and issecretvalue(name) then name = "" end
	name = name:sub(1, 24)
	pushBits(bits, #name, 5)
	for i = 1, 24 do pushBits(bits, name:byte(i) or 0, 8) end
	-- v3: your arrow's size (settings) and your class colour (your dot on your friends' maps)
	pushBits(bits, arrowSize() * 10, 5)
	local r, g, b = classColor("player")
	pushBits(bits, r * 31, 5)
	pushBits(bits, g * 31, 5)
	pushBits(bits, b * 31, 5)
	-- v4: how big the tracker draws your teammates' dots
	pushBits(bits, sizeOf("dotSize") * 10, 5)
	-- v5: cheap run context; boss indexes follow ns.Bosses, exactly as the tracker data.
	pushBits(bits, d and activeEncounter and activeEncounter.key == d.key and activeEncounter.index or 0, 6)
	local mask = 0
	if d then
		for i = 1, math.min(32, #(ns.Bosses[d.key] or {})) do
			if bossDone(d.key, i) then mask = mask + 2 ^ (i - 1) end
		end
	end
	pushBits(bits, mask, 32)
	pushBits(bits, DungeonMapsDB.contribute ~= false and 1 or 0, 1)
	pushBits(bits, (coversMinimap(GameTooltip) or coversMinimap(ShoppingTooltip1)
		or coversMinimap(ShoppingTooltip2) or coversMinimap(map)
		or coversMinimap(WorldMapFrame)) and 1 or 0, 1)
	local cells, sum = beaconOut, 0
	for c = 1, BEACON_CELLS - #HEADER - 1 do
		local v = 0
		for b = 1, 9 do v = v * 2 + (bits[(c - 1) * 9 + b] or 0) end
		cells[c] = v
		sum = sum + v
	end
	cells[BEACON_CELLS - #HEADER] = sum % 512
	return cells, d ~= nil
end

local function placeBeacon()
	-- Stay on the top edge, horizontally beside the minimap. Screenshot fallback
	-- can capture a small rectangle instead of the entire span across the game.
	local physW, physH = GetPhysicalScreenSize()
	local k = physH / (UIParent:GetHeight() * UIParent:GetEffectiveScale())
	local unit = 1 / (beacon:GetEffectiveScale() * k) -- one physical pixel in UI units
	beacon:SetSize(BEACON_CELLS * BEACON_PX * unit, BEACON_PX * unit)
	for i, t in ipairs(beacon.cells) do
		t:SetSize(BEACON_PX * unit, BEACON_PX * unit)
		t:ClearAllPoints()
		t:SetPoint("TOPLEFT", beacon, "TOPLEFT", (i - 1) * BEACON_PX * unit, 0)
		if t.SetSnapToPixelGrid then
			t:SetSnapToPixelGrid(false)
			t:SetTexelSnappingBias(0)
		end
	end
	beacon:ClearAllPoints()
	local mx = Minimap and pixelRect(Minimap)
	local x = math.floor(math.max(0, math.min(physW - BEACON_CELLS * BEACON_PX, mx or 0)) + 0.5)
	beacon:SetPoint("TOPLEFT", UIParent, "TOPLEFT", x * unit, 0)
end

local function updateBeacon()
	local cells, active = beaconCells()
	beacon:SetShown(active)
	for i, v in ipairs(cells) do
		local t = beacon.cells[#HEADER + i]
		if t.value ~= v then
			t.value = v
			t:SetColorTexture(math.floor(v / 64) % 8 / 7, math.floor(v / 8) % 8 / 7, v % 8 / 7, 1)
		end
	end
end

-- the map opening or closing changes the beacon in that same frame (not at the next tick): the
-- tracker's arrow must vanish the instant the map does
local mapHooked = false
local function hookMap()
	if mapHooked or not map then return end
	mapHooked = true
	local function now()
		if beacon and beacon:IsShown() then updateBeacon() end
	end
	map:HookScript("OnHide", now)
	map:HookScript("OnShow", now)
end

local function buildBeacon()
	if beacon or not Minimap then return end
	beacon = CreateFrame("Frame", "DungeonMapsBeacon", UIParent)
	beacon:SetFrameStrata("TOOLTIP")
	beacon:SetFrameLevel(9000)
	beacon:SetIgnoreParentAlpha(true)
	beacon.cells = {}
	for i = 1, BEACON_CELLS do
		local t = beacon:CreateTexture(nil, "OVERLAY")
		local h = HEADER[i]
		if h then t:SetColorTexture(h[1] / 7, h[2] / 7, h[3] / 7, 1) end
		beacon.cells[i] = t
	end
	placeBeacon()
	beacon:Hide()
	local ticker = CreateFrame("Frame")
	local elapsed, placed = 0, 0
	ticker:SetScript("OnUpdate", function(_, dt)
		elapsed, placed = elapsed + dt, placed + dt
		if elapsed < 0.03 then return end -- (the tracker reads it every frame the game draws)
		elapsed = 0
		if DungeonMapsDB.live == false or not inDungeon() then
			beacon:Hide()
			return
		end
		if placed > 2 then -- (UI scale, minimap moves)
			placed = 0
			placeBeacon()
		end
		hookMap()
		updateBeacon()
	end)
end

---------------------------------------------------------------------------------------------------
-- Map key swap
---------------------------------------------------------------------------------------------------

local function applyBindings()
	if InCombatLockdown() then
		bindingsPending = true
		return
	end
	bindingsPending = false
	ClearOverrideBindings(events)
	if not (inMappedArea() and findDungeon()) then return end
	for _, key in ipairs({ GetBindingKey("TOGGLEWORLDMAP") }) do
		SetOverrideBinding(events, true, key, "DUNGEONMAPS_TOGGLE")
	end
end

function DungeonMaps_Toggle()
	if map and map:IsShown() then
		map:Hide()
	elseif inMappedArea() then
		openMap()
	else
		toggleWorldMap()
	end
end

local function resetBossProgress(d)
	if not d then
		say("go into a dungeon first.")
		return
	end
	if DungeonMapsCharDB.runs then DungeonMapsCharDB.runs[d.key] = nil end
	GameTooltip:Hide()
	refreshPeople()
	say("defeated bosses cleared for " .. d.name .. ".")
end

SLASH_DUNGEONMAPS1 = "/dmaps"
SLASH_DUNGEONMAPS2 = "/dmk"
SlashCmdList.DUNGEONMAPS = function(input)
	local cmd = strtrim(input or ""):lower()
	if cmd == "diag" then
		if not inDungeon() then
			say("go into a dungeon first.")
			return
		end
		if not (map and map:IsShown()) then openMap() end
		local d = recordDiag()
		say(("%s: sub-zone \"%s\", room %s, landmark %s, floor %s"):format(tostring(d.instanceName),
			tostring(d.subzone), tostring(d.room), tostring(d.landmark), tostring(d.shownFloor)))
		for _, line in ipairs(d.group) do say("  " .. line) end
		say("saved for Claude.")
	elseif cmd == "live" then
		DungeonMapsDB.live = DungeonMapsDB.live == false
		refreshPeople()
		say(DungeonMapsDB.live and "live mode ON: the beacon strip by the minimap is shown and the screen tracker draws your arrow (your landmark dot is hidden)."
			or "live mode OFF: no beacon; your dot is the last landmark again.")
	elseif cmd:match("^size") then
		local v = tonumber(cmd:match("^size%s+([%d%.]+)"))
		if v then
			DungeonMapsDB.arrowSize = math.max(ARROW_MIN, math.min(ARROW_MAX, v))
			if ns.refreshSettings then ns.refreshSettings() end
		end
		say(("your arrow size: %.1fx (%.1f to %.1f: /dmaps size 1.5)"):format(arrowSize(), ARROW_MIN, ARROW_MAX))
	elseif cmd:match("^dots") or cmd:match("^bosses") then
		local key = cmd:match("^dots") and "dotSize" or "bossSize"
		local v = tonumber(cmd:match("%s+([%d%.]+)"))
		if v then
			DungeonMapsDB[key] = math.max(SIZE_MIN, math.min(SIZE_MAX, v))
			if ns.refreshSettings then ns.refreshSettings() end
			refreshPeople()
		end
		say(("%s size: %.1fx (%.1f to %.1f)"):format(key == "dotSize" and "teammate dot" or "boss icon", sizeOf(key), SIZE_MIN, SIZE_MAX))
	elseif cmd == "others" then
		DungeonMapsDB.showOthers = not DungeonMapsDB.showOthers
		if ns.refreshSettings then ns.refreshSettings() end
		refreshPeople()
		say(DungeonMapsDB.showOthers and "teammates without Dungeon Maps are shown (rough spots)." or "only teammates with Dungeon Maps are shown.")
	elseif cmd == "settings" or cmd == "options" then
		if ns.settingsCategory and Settings and Settings.OpenToCategory then
			Settings.OpenToCategory(ns.settingsCategory:GetID())
		elseif InterfaceOptionsFrame_OpenToCategory and ns.settingsPanel then
			InterfaceOptionsFrame_OpenToCategory(ns.settingsPanel)
		end
	elseif cmd == "reset" then
		resetBossProgress(inDungeon() and findDungeon())
	else
		local keys = { GetBindingKey("TOGGLEWORLDMAP") }
		say(("map key: %s; in a dungeon now: %s. /dmaps settings = options, /dmaps size 1.5 = your arrow size, /dmaps dots 1.5 and /dmaps bosses 1.5 = marker sizes, /dmaps others = teammates without the add-on on/off, /dmaps reset = clear boss kills, /dmaps live = live tracker beacon on/off, /dmaps diag = what the game reports here."):format(
			#keys > 0 and table.concat(keys, ", ") or "none", inDungeon() and "yes" or "no"))
	end
end

---------------------------------------------------------------------------------------------------
-- Settings panel (Esc > Options > AddOns > Dungeon Maps)
---------------------------------------------------------------------------------------------------

-- The settings, built twice: in the map's gear menu and in Esc > Options > AddOns > Dungeon Maps.
local sliderCount = 0
local settingsRefreshers = {}

local function redrawMap()
	if map and map:IsShown() and floorIndex then
		drawBosses(floors[floorIndex])
		refreshPeople()
	end
end

local function addSettingsControls(parent, x, y, width)
	local refreshers = {}
	local function check(text, get, set)
		local c = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
		c:SetPoint("TOPLEFT", x - 4, y)
		local t = c:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
		t:SetPoint("LEFT", c, "RIGHT", 2, 1)
		t:SetWidth(width - 34)
		t:SetJustifyH("LEFT")
		t:SetText(text)
		c:SetScript("OnClick", function(self)
			set(self:GetChecked() and true or false)
			for _, f in ipairs(settingsRefreshers) do f() end
			redrawMap()
		end)
		refreshers[#refreshers + 1] = function() c:SetChecked(get()) end
		y = y - 34
	end
	local function slider(text, key)
		sliderCount = sliderCount + 1
		local name = "DungeonMapsSizeSlider" .. sliderCount
		local sl = CreateFrame("Slider", name, parent, "OptionsSliderTemplate")
		sl:SetPoint("TOPLEFT", x + 4, y - 16)
		sl:SetWidth(width - 20)
		sl:SetMinMaxValues(SIZE_MIN, SIZE_MAX)
		sl:SetValueStep(0.1)
		if sl.SetObeyStepOnDrag then sl:SetObeyStepOnDrag(true) end
		-- (OptionsSliderTemplate names its labels after the slider)
		local label, low, high = _G[name .. "Text"], _G[name .. "Low"], _G[name .. "High"]
		if low then low:SetText(("%.1fx"):format(SIZE_MIN)) end
		if high then high:SetText(("%.1fx"):format(SIZE_MAX)) end
		local function show()
			if label then label:SetText(("%s: %.1fx"):format(text, sizeOf(key))) end
		end
		sl:SetScript("OnValueChanged", function(_, v)
			v = math.floor(v * 10 + 0.5) / 10
			if v == sizeOf(key) and DungeonMapsDB[key] then return show() end
			DungeonMapsDB[key] = v
			show()
			redrawMap()
		end)
		refreshers[#refreshers + 1] = function()
			sl:SetValue(sizeOf(key))
			show()
		end
		y = y - 54
	end
	check("Show teammates who don't have Dungeon Maps (rough spots: their room, or near you)",
		function() return DungeonMapsDB.showOthers == true end, function(v) DungeonMapsDB.showOthers = v end)
	check("Live tracker (the small colour strip in the top-left corner the tracker reads)",
		function() return DungeonMapsDB.live ~= false end, function(v) DungeonMapsDB.live = v end)
	check("Share Shift+click corrections and minimap pictures to improve maps (20 per dungeon)",
		function() return DungeonMapsDB.contribute ~= false end, function(v) DungeonMapsDB.contribute = v end)
	check("Wailing Caverns: show the route guide on the instance map",
		function() return DungeonMapsDB.wailingRoute ~= false end,
		function(v)
			DungeonMapsDB.wailingRoute = v
			if map and map:IsShown() and dungeon and dungeon.key == "wailingcaverns" then showFloor(floorIndex) end
		end)
	slider("Your arrow", "arrowSize")
	slider("Teammate dots", "dotSize")
	slider("Boss icons", "bossSize")
	local reset = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
	reset:SetPoint("TOPLEFT", x, y - 4)
	reset:SetSize(math.min(width - 16, 220), 24)
	reset:SetText("Clear defeated bosses")
	reset:SetScript("OnClick", function()
		-- The map button applies to the displayed wing; the Options panel uses
		-- the dungeon we're currently in. Never clear another dungeon's progress.
		local d = (map and parent == map.settings and dungeon) or (inDungeon() and findDungeon())
		resetBossProgress(d)
	end)
	reset:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
		GameTooltip:SetText("Clear defeated bosses")
		GameTooltip:AddLine("Mark this dungeon's bosses as undefeated again. Your arrow and learned map data stay intact.", 1, 1, 1, true)
		GameTooltip:Show()
	end)
	reset:SetScript("OnLeave", function() GameTooltip:Hide() end)
	parent.resetBosses = reset
	y = y - 38
	local function refresh() for _, f in ipairs(refreshers) do f() end end
	settingsRefreshers[#settingsRefreshers + 1] = refresh
	return refresh, y
end

-- The gear at the map's top right: the same settings, right on the map.
function ns.makeGear(frame)
	local gear = CreateFrame("Button", nil, frame)
	gear:SetSize(22, 22)
	gear:SetPoint("RIGHT", frame.closeButton, "LEFT", -2, 0)
	gear:SetNormalTexture("Interface\\Buttons\\UI-OptionsButton")
	gear:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
	local panel = CreateFrame("Frame", nil, frame, "BackdropTemplate")
	panel:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -PAD - 4, -(PAD + BAR_H) - 4)
	panel:SetFrameLevel(frame.canvas:GetFrameLevel() + 60)
	panel:SetBackdrop({
		bgFile = "Interface\\ChatFrame\\ChatFrameBackground",
		edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
		edgeSize = 14,
		insets = { left = 3, right = 3, top = 3, bottom = 3 },
	})
	panel:SetBackdropColor(0.05, 0.04, 0.03, 0.95)
	panel:SetBackdropBorderColor(0.8, 0.65, 0.3, 1)
	panel:EnableMouse(true) -- (clicks here never reach the map below)
	local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
	title:SetPoint("TOPLEFT", 14, -12)
	title:SetText("Map settings")
	local refresh, y = addSettingsControls(panel, 16, -38, 320)
	local hint = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	hint:SetPoint("TOPLEFT", 14, y - 4)
	hint:SetWidth(310)
	hint:SetJustifyH("LEFT")
	hint:SetText("Shift+click the map where you stand to place your arrow.")
	panel:SetSize(346, -y + 34)
	panel:Hide()
	gear:SetScript("OnClick", function()
		panel:SetShown(not panel:IsShown())
		if panel:IsShown() then refresh() end
	end)
	gear:SetScript("OnEnter", function(self)
		GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
		GameTooltip:SetText("Map settings")
		GameTooltip:AddLine("Teammates, live tracker, marker sizes, and clearing defeated bosses.", 1, 1, 1, true)
		GameTooltip:Show()
	end)
	gear:SetScript("OnLeave", function() GameTooltip:Hide() end)
	frame:HookScript("OnHide", function() panel:Hide() end)
	frame.gear, frame.settings = gear, panel
end

local function createSettings()
	local panel = CreateFrame("Frame")
	panel.name = "Dungeon Maps"
	local title = panel:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
	title:SetPoint("TOPLEFT", 16, -16)
	title:SetText("Dungeon Maps")
	local sub = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
	sub:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -8)
	sub:SetWidth(560)
	sub:SetJustifyH("LEFT")
	sub:SetText("Your map key opens the dungeon map inside dungeons. With the Dungeon Maps tracker running, "
		.. "your live arrow and your group's dots are drawn on it. Shift+click the map where you stand to place your arrow. "
		.. "The gear on the map has these settings too.")
	local refresh = addSettingsControls(panel, 16, -70, 460)
	panel:SetScript("OnShow", refresh)

	ns.refreshSettings, ns.settingsPanel = function() for _, f in ipairs(settingsRefreshers) do f() end end, panel
	if Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterAddOnCategory then
		local category = Settings.RegisterCanvasLayoutCategory(panel, "Dungeon Maps")
		Settings.RegisterAddOnCategory(category)
		ns.settingsCategory = category
	elseif InterfaceOptions_AddCategory then
		InterfaceOptions_AddCategory(panel)
	end
end
createSettings()

---------------------------------------------------------------------------------------------------
-- Events
---------------------------------------------------------------------------------------------------

if C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix then
	C_ChatInfo.RegisterAddonMessagePrefix(PREFIX)
end

events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:RegisterEvent("PLAYER_LEAVING_WORLD")
events:RegisterEvent("ZONE_CHANGED_NEW_AREA")
events:RegisterEvent("ZONE_CHANGED")
events:RegisterEvent("ZONE_CHANGED_INDOORS")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:RegisterEvent("GROUP_ROSTER_UPDATE")
events:RegisterEvent("ENCOUNTER_START")
events:RegisterEvent("INSTANCE_ENCOUNTER_ENGAGE_UNIT")
events:RegisterEvent("ENCOUNTER_END")
events:RegisterEvent("BOSS_KILL")
events:RegisterEvent("CHAT_MSG_ADDON")
events:RegisterEvent("CHAT_MSG_SYSTEM")
events:SetScript("OnEvent", function(_, event, arg1, arg2, arg3, arg4, arg5)
	if event == "PLAYER_LEAVING_WORLD" then
		enteringDead = plain(UnitIsDeadOrGhost("player")) == true
		return
	elseif event == "PLAYER_REGEN_ENABLED" then
		if bindingsPending then applyBindings() end
		return
	elseif event == "GROUP_ROSTER_UPDATE" then
		if not channel() then members = {} end
		send("W")
		sendState(true)
		refreshPeople()
		return
	elseif event == "CHAT_MSG_ADDON" then
		onAddonMessage(arg1, arg2, arg4)
		return
	elseif event == "ZONE_CHANGED" or event == "ZONE_CHANGED_INDOORS" then
		sendState()
		applyBindings()
		if map and map:IsShown() then
			local d = findDungeon()
			if not d then map:Hide() elseif d ~= dungeon then setDungeon(d) end
		end
		return
	elseif event == "ENCOUNTER_START" then
		landmarkBoss(arg1, arg2)
		learnBossLabel()
		refreshPeople()
		return
	elseif event == "INSTANCE_ENCOUNTER_ENGAGE_UNIT" then
		learnBossLabel()
		refreshPeople()
		return
	elseif event == "ENCOUNTER_END" or event == "BOSS_KILL" then
		activeEncounter = nil
		-- ENCOUNTER_END: encounterID, name, difficulty, group size, success (1 = kill)
		if event == "BOSS_KILL" or plain(arg5) == 1 then onBossKilled(arg1, arg2) end
		refreshPeople()
		return
	elseif event == "CHAT_MSG_SYSTEM" then
		-- "<instance> has been reset.": its boss kills start over
		local text = plain(arg1)
		if type(text) == "string" and text:find("reset") then
			for _, d in ipairs(ns.Dungeons) do
				if text:find(d.name, 1, true) then clearInstanceRun(d.instanceID) end
			end
			refreshPeople()
		end
		return
	end
	if event == "PLAYER_ENTERING_WORLD" then
		activeEncounter = nil
		checkRunEntry(arg1, arg2)
		if not DungeonMapsDB.samplesNotice then
			say("Shift+click corrections share small minimap pictures to improve maps (up to 20 per dungeon). Turn sharing off in /dmaps settings.")
			DungeonMapsDB.samplesNotice = true
		end
		quietRoutes()
		C_Timer.After(2.5, quietRoutes) -- (its small map opens 2 s after the loading screen)
		buildBackButton()
		buildBeacon()
		-- arg1 = initial login, arg2 = UI reload: only a real zone-in puts you at the entrance
		if not plain(arg2) then
			lastRoom = {}
			landmark = nil
			if inDungeon() and not plain(arg1) then landmarkEntrance() end
		end
		sendState(true)
		refreshPeople()
	end
	applyBindings()
	if map and map:IsShown() and not inMappedArea() then map:Hide() end
end)
