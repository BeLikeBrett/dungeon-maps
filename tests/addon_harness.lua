local ADDONS = arg[1]
-- generic no-op widget: any method returns nil except those defined
local placed = {}
local function widget(kind)
  local w = { _shown = (kind ~= "Frame"), _kind = kind, _pts = {} }
  return setmetatable(w, { __index = function(t, k)
    if k == "IsShown" then return function(s) return s._shown end end
    if k == "Show" then return function(s) s._shown = true end end
    if k == "Hide" then return function(s) s._shown = false end end
    if k == "SetShown" then return function(s, v) s._shown = not not v end end
    if k == "GetStringWidth" then return function() return 100 end end
    if k == "GetFrameLevel" then return function() return 1 end end
    if k == "GetHeight" or k == "GetWidth" then return function() return 1080 end end
    if k == "SetText" then return function(s, v) s._text = v end end
    if k == "SetPoint" then return function(s, ...) s._pts = {...} end end
    if k == "SetAlpha" then return function(s, v) s._alpha = v end end
    if k == "CreateTexture" or k == "CreateFontString" then return function() return widget("Region") end end
    if k == "SetTexture" then return function(s, value) s._texture = value return true end end
    if k == "SetTexCoord" then return function(s, ...) s._texcoord = {...} end end
    if k == "SetDrawLayer" then return function(s, layer, level) s._layer, s._level = layer, level end end
    if k == "SetSize" then return function(s, width, height) s._width, s._height = width, height end end
    if k == "SetScript" then return function(s, ev, fn) local t = rawget(s, "_scripts") or {} rawset(s, "_scripts", t) t[ev] = fn end end
    if k == "StartMoving" or k == "StopMovingOrSizing" then return function() end end
    return function() end
  end })
end
ALLFRAMES = {}
CreateFrame = function(kind, name) local w = widget(kind) if name then _G[name] = w end ALLFRAMES[#ALLFRAMES+1] = w return w end
UIParent = widget("Frame"); UIParent._shown = true
UISpecialFrames = {}; tinsert = table.insert
STANDARD_TEXT_FONT = "x"
DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) print("CHAT", m) end }
GameTooltip = widget("Frame")
RAID_CLASS_COLORS = { PRIEST = {r=1,g=1,b=1}, DRUID = {r=1,g=.49,b=.04}, MAGE = {r=.25,g=.78,b=.92} }
SlashCmdList = {}
strtrim = function(s) return (s:gsub("^%s+",""):gsub("%s+$","")) end
date = os.date
issecret = function() return false end
function GetTime() return os.clock() end
function IsInInstance() return true, "party" end
function GetInstanceInfo() return "Ragefire Chasm", "party", 1, "", 5, 0, false, 389 end
function GetBuildInfo() return "1.60.1", "70959" end
function GetSubZoneText() return "" end
function UnitName(u) local n = { player = "Breziath", party1 = "Byai", party2 = "Thicc", party3 = "Kanoa", party4 = "Bearly" } return n[u] end
function UnitClass(u) local c = { party1 = "DRUID", party2 = "MAGE", party3 = "PRIEST", party4 = "DRUID" } return c[u], c[u] end
function UnitExists(u) return UnitName(u) ~= nil end
function UnitIsUnit(a, b) return a == b end
function UnitIsDeadOrGhost(u) return u == "party4" end
function UnitIsConnected() return true end
function CheckInteractDistance(u) return u == "party2" end
function UnitInRange(u) return u == "party2" or u == "party3" end
function IsInRaid() return false end
function GetNumSubgroupMembers() return 0 end
function GetNumGroupMembers() return 5 end
function InCombatLockdown() return false end
function ClearOverrideBindings() end
function SetOverrideBinding(_, _, key, cmd) print("BIND", key, cmd) end
function GetBindingKey() return "G" end
WorldMapFrame = nil
function ToggleWorldMap() if WorldMapFrame:IsShown() then WorldMapFrame:Hide() else WorldMapFrame:Show() end print("WORLDMAP toggled ->", WorldMapFrame:IsShown()) end
function UnitPosition() return nil, nil, nil, 36 end
function GetPlayerFacing() return nil end
function Ambiguate(n) return (n:match("^[^-]+")) end
C_Map = { GetBestMapForUnit = function() return nil end }
C_Timer = { After = function() end }

-- NO Forever Dungeon Routes: the addon must stand alone
ForeverDungeonRoutes = nil
function GetMinimapZoneText() return "" end
C_ChatInfo = { RegisterAddonMessagePrefix = function() end, SendAddonMessage = function(p, t, ch) print("SEND", p, (t:gsub("\t", " | ")), ch) end }
function IsInGroup() return false end
function time() return os.time() end
DungeonMapsDB, DungeonMapsCharDB = nil, nil
local ns = {}
assert(loadfile(ADDONS .. "/DungeonMaps/Data.lua"))("DungeonMaps", ns)
assert(loadfile(ADDONS .. "/DungeonMaps/Approaches.lua"))("DungeonMaps", ns)
assert(loadfile(ADDONS .. "/DungeonMaps/DungeonMaps.lua"))("DungeonMaps", ns)
print("dungeons", #ns.Dungeons, "rfc bosses", #ns.Bosses.ragefire, "hallofthanes image", ns.Floors[1030651].image.file)
WorldMapFrame = widget("Frame"); WorldMapFrame._shown = false
WorldMapFrame.SetMapID = function(self, id) print("WORLDMAP SetMapID", id) end
local function fire(ev, ...)
  for _, f in ipairs(ALLFRAMES) do local sc = rawget(f, "_scripts") if sc and sc.OnEvent and f ~= DungeonMapsFrame then sc.OnEvent(f, ev, ...) end end
end
local function dump(label)
  local m = DungeonMapsFrame
  print("--- " .. label)
  for _, b in ipairs(m.bosses) do if b._shown then print(("boss %s at (%.0f, %.0f) %s | %s"):format(b.num._text, b._pts[4], -b._pts[5], b.tipTitle, table.concat(b.tipLines, " / "))) end end
  for _, d in ipairs(m.dots) do if d._shown then print(("dot %-4s at (%.0f, %.0f) alpha %.2f  %s"):format(d.label._text, d._pts[4], -d._pts[5], d._alpha or 1, table.concat(d.tipLines, " "))) end end
  for _, l in ipairs(m.legend.lines) do if l.text._shown then print("legend", (l.text._text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""))) end end
end
fire("PLAYER_ENTERING_WORLD", false, false)
DungeonMaps_Toggle()
dump("just zoned in")
fire("ENCOUNTER_START", 2735, "Bazzalan")
fire("ENCOUNTER_END", 2735, "Bazzalan", 1, 5, 1)
rawget(DungeonMapsFrame, "_scripts").OnUpdate(DungeonMapsFrame, 1)
dump("Bazzalan pulled")
-- teammates without Dungeon Maps (no group messages from them): hidden unless the setting is on
local function shownDots()
  local n = 0
  for _, d in ipairs(DungeonMapsFrame.dots) do if d._shown and d.label._text ~= "You" then n = n + 1 end end
  return n
end
IsInGroup = function() return true end; GetNumSubgroupMembers = function() return 4 end
rawget(DungeonMapsFrame, "_scripts").OnUpdate(DungeonMapsFrame, 1)
assert(shownDots() == 0, "teammates without the addon must be hidden by default, got " .. shownDots())
DungeonMapsDB.showOthers = true
rawget(DungeonMapsFrame, "_scripts").OnUpdate(DungeonMapsFrame, 1)
assert(shownDots() > 0, "showOthers on: teammates must be drawn")
print("OK teammates without the addon: hidden by default,", shownDots(), "drawn with the setting on")
DungeonMapsDB.showOthers = nil
IsInGroup = function() return false end; GetNumSubgroupMembers = function() return 0 end
-- the gear opens the map settings; sizes change the markers
local gear = DungeonMapsFrame.gear
rawget(gear, "_scripts").OnClick(gear)
assert(DungeonMapsFrame.settings._shown, "gear must open the settings")
local reset = assert(rawget(DungeonMapsFrame.settings, "resetBosses"), "map settings need a boss reset button")
assert(reset._text == "Clear defeated bosses")
local unrelated = {t = time(), killed = {[1] = true}}
DungeonMapsCharDB.runs.unrelated = unrelated
assert(DungeonMapsCharDB.runs.ragefire, "test must start with a defeated boss")
rawget(reset, "_scripts").OnClick(reset)
assert(not DungeonMapsCharDB.runs.ragefire, "map settings reset did not clear boss progress")
assert(DungeonMapsCharDB.runs.unrelated == unrelated, "button cleared another dungeon")
for _, boss in ipairs(DungeonMapsFrame.bosses) do
  if boss:IsShown() then assert(not boss.tipLines[1]:find("defeated"), "reset did not redraw defeated label") end
end
rawget(reset, "_scripts").OnClick(reset) -- already clear: harmless
print("OK map settings button clears and redraws only this dungeon's defeated bosses")
DungeonMapsDB.bossSize = 2
rawget(DungeonMapsFrame, "_scripts").OnUpdate(DungeonMapsFrame, 1)
print("OK gear settings open; boss icon size setting 2.0x")
-- Shift+click places you (a plain click doesn't)
local c = DungeonMapsFrame.canvas
rawset(c, "GetLeft", function() return 0 end); rawset(c, "GetTop", function() return 668 end)
rawset(c, "GetWidth", function() return 1002 end); rawset(c, "GetHeight", function() return 668 end)
rawset(c, "GetEffectiveScale", function() return 1 end)
GetCursorPosition = function() return 501, 334 end
local up = rawget(DungeonMapsFrame, "_scripts").OnMouseUp
IsShiftKeyDown = function() return false end
up(DungeonMapsFrame, "LeftButton")
local before = DungeonMapsCharDB and DungeonMapsCharDB.landmark
IsShiftKeyDown = function() return true end
up(DungeonMapsFrame, "LeftButton")
dump("shift+clicked the middle")
local found = false
for _, l in ipairs(DungeonMapsFrame.legend.lines) do
  if l.text._shown and (l.text._text or ""):find("marked") then found = true end
end
assert(found, "Shift+click must mark your position")
assert(before == nil or before ~= (DungeonMapsCharDB and DungeonMapsCharDB.landmark), "a plain click must not mark")
print("OK Shift+click marks where you stand")
IsShiftKeyDown = function() return false end
print("back button shown:", DungeonMapsBackButton and DungeonMapsBackButton._shown)
-- World Map button = first UIPanelButtonTemplate child created in buildMap; find by text
for _, f in ipairs(ALLFRAMES) do if f._text == "World Map" then rawget(f, "_scripts").OnClick(f) end end
print("dungeon map shown after World Map click:", DungeonMapsFrame._shown, "world map shown:", WorldMapFrame._shown)
rawget(DungeonMapsBackButton, "_scripts").OnClick(DungeonMapsBackButton)
print("after Dungeon Map click: dungeon map", DungeonMapsFrame._shown, "world map", WorldMapFrame._shown)
-- Every bundled picture must be selected through the real addon without FDR or addon-discovery APIs.
local pictures = 0
for _, d in ipairs(ns.Dungeons) do
  for _, floor in ipairs(d.floors) do
    local info = ns.Floors[floor]
    if info and info.image then
      GetInstanceInfo = function() return d.name, "party", 1, "", 5, 0, false, d.instanceID end
      C_Map.GetBestMapForUnit = function() return floor end
      DungeonMapsFrame:Hide()
      DungeonMaps_Toggle()
      local m = DungeonMapsFrame
      assert(m.picture._shown and not m.noArt._shown, "picture hidden for floor " .. floor)
      local file = info.image.routeFile or info.image.file
      assert(m.picture._texture == "Interface\\AddOns\\DungeonMaps\\" .. file, m.picture._texture)
      assert(m.picture._texcoord[2] == (info.image.right or 1) and m.picture._texcoord[4] == (info.image.bottom or 1))
      local file = assert(io.open(ADDONS .. "/DungeonMaps/" .. info.image.file:gsub("\\", "/") .. ".blp", "rb"))
      assert(file:read(4) == "BLP2", "invalid BLP image for floor " .. floor)
      file:close()
      pictures = pictures + 1
    end
  end
end
assert(pictures == 18, "expected 17 Santiago maps and one WC instance map, got " .. pictures)
print("OK 18 bundled instance pictures loaded without Forever Dungeon Routes")
-- Wailing Caverns must display all building parts, including the omitted east
-- wing, without changing its marker coordinates or other floors' artwork.
GetInstanceInfo = function() return "Wailing Caverns", "party", 1, "", 5, 0, false, 43 end
C_Map.GetBestMapForUnit = function() return 279 end
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
local terrain = ns.MinimapArt[279]
assert(ns.Floors[279].terrain and #terrain == 43)
assert(DungeonMapsFrame.picture:IsShown() and DungeonMapsFrame.picture._texture:find("wailing_caverns_route"))
DungeonMapsDB.wailingRoute = false
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
assert(DungeonMapsFrame.picture._texture:find("wailing_caverns_instance"))
DungeonMapsDB.wailingRoute = true
-- New image files need a full game start on some clients. Exercise the safe
-- instance-only fallback while preserving the request to restart.
local setPicture = DungeonMapsFrame.picture.SetTexture
rawset(DungeonMapsFrame.picture, "SetTexture", function() return false end)
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
assert(DungeonMapsFrame.terrainBack:IsShown() and not DungeonMapsFrame.picture:IsShown())
for _, tex in ipairs(DungeonMapsFrame.tiles) do assert(not tex:IsShown(), "incomplete parchment still visible") end
for i, part in ipairs(terrain) do
  local tex = DungeonMapsFrame.terrainTiles[i]
  assert(tex:IsShown() and tex._texture == part[1], "missing terrain part " .. i)
  assert(tex._pts[4] == part[2] and tex._pts[5] == -part[3])
  assert(tex._width == part[4] and tex._height == part[5] and tex._level == part[14])
  for j=1,8 do assert(tex._texcoord[j] == part[j+5], "terrain orientation changed") end
end
for i, boss in ipairs(ns.Bosses.wailingcaverns) do
  local pin = DungeonMapsFrame.bosses[i]
  assert(pin.tipTitle == boss.name and pin._pts[4] == boss.x * 1002 and pin._pts[5] == -boss.y * 668)
end
local retained = DungeonMapsFrame.terrainTiles[1]
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
assert(DungeonMapsFrame.terrainTiles[1] == retained, "reopening allocated duplicate terrain")
rawset(DungeonMapsFrame.picture, "SetTexture", setPicture)
GetInstanceInfo = function() return "Ragefire Chasm", "party", 1, "", 5, 0, false, 389 end
C_Map.GetBestMapForUnit = function() return 213 end
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
assert(not DungeonMapsFrame.terrainBack:IsShown())
for _, tex in ipairs(DungeonMapsFrame.terrainTiles) do assert(not tex:IsShown(), "WC terrain leaked onto another map") end
for _, tex in ipairs(DungeonMapsFrame.tiles) do assert(tex:IsShown(), "another floor lost its original art") end
print("OK Wailing Caverns complete terrain, unchanged pins, texture reuse, and floor isolation")

-- Entering the approach without crossing the instance portal opens a separate
-- map. Its marks and boss state must never become an instance player fix.
local realInstance, realSubzone = IsInInstance, GetSubZoneText
IsInInstance = function() return false, "none" end
GetSubZoneText = function() return "Cavern of Mists" end
fire("ZONE_CHANGED")
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
assert(DungeonMapsFrame:IsShown() and DungeonMapsFrame.title._text:find("Approach cave"))
assert(DungeonMapsFrame.picture._texture:find("wailing_caverns_approach"))
assert(DungeonMapsFrame.portal:IsShown())
for _,boss in ipairs(DungeonMapsFrame.bosses) do assert(not boss:IsShown(), "instance boss leaked onto approach") end
GetSubZoneText = function() return "The Barrens" end
fire("ZONE_CHANGED")
assert(not DungeonMapsFrame:IsShown(), "approach map stayed after leaving the cave")
-- The same room text inside the real instance must never select the approach.
IsInInstance = realInstance
GetInstanceInfo = function() return "Wailing Caverns", "party", 1, "", 5, 0, false, 43 end
C_Map.GetBestMapForUnit = function() return 279 end
GetSubZoneText = function() return "Cavern of Mists" end
fire("PLAYER_ENTERING_WORLD", false, false)
DungeonMaps_Toggle()
assert(DungeonMapsFrame.title._text == "Wailing Caverns" and not DungeonMapsFrame.portal:IsShown())
assert(DungeonMapsFrame.bosses[4]:IsShown())
GetSubZoneText = realSubzone
print("OK approach/portal/real-instance boundaries and unrelated outdoor zones")

-- Exercise every imported name/alias against the addon's actual kill matcher.
-- This includes shared encounter IDs, without assuming the first pin is correct.
DungeonMapsFrame:Hide()
local pins, labels = 0, 0
for _, d in ipairs(ns.Dungeons) do
  GetInstanceInfo = function() return d.name, "party", 1, "", 5, 0, false, d.instanceID end
  C_Map.GetBestMapForUnit = function() return d.floors[1] end
  for i, boss in ipairs(ns.Bosses[d.key] or {}) do
    pins = pins + 1
    local names = {boss.name}
    for _, alias in ipairs(boss.aliases or {}) do names[#names+1] = alias end
    for _, name in ipairs(names) do
      DungeonMapsCharDB.runs[d.key] = nil
      fire("ENCOUNTER_END", 0, name, 1, 5, 1)
      local progress = DungeonMapsCharDB.runs[d.key]
      assert(progress and progress.killed[i], d.key .. " failed name: " .. name)
      for other in pairs(progress.killed) do assert(other == i, "name resolved another boss: " .. name) end
      labels = labels + 1
    end
  end
end
assert(pins == 212)
print("OK all 212 boss pins and " .. labels .. " names/aliases resolve correctly")
-- Creature display names and encounter titles must both resolve to the same pin.
GetInstanceInfo = function() return "Ruins of Lordaeron", "party", 1, "", 5, 0, false, 2999 end
C_Map.GetBestMapForUnit = function() return 1029991 end
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
fire("ENCOUNTER_END", 0, "The Butcher", 1, 5, 1)
assert(DungeonMapsCharDB.runs.ruinsoflordaeron.killed[2])
local originalUnitName = UnitName
UnitName = function(u) if u == "boss1" then return "The Baron (live)" end return originalUnitName(u) end
fire("ENCOUNTER_START", 3355, "The Butcher")
assert(DungeonMapsDB.bossNames["enUS:3355"] == "The Baron (live)")
assert(DungeonMapsFrame.bosses[2].tipTitle == "The Baron (live)")
fire("ENCOUNTER_END", 3355, "The Butcher", 1, 5, 0)
UnitName = originalUnitName
-- A shared encounter must not replace two individual boss names with one unit's name.
GetInstanceInfo = function() return "Scarlet Monastery", "party", 1, "", 5, 0, false, 189 end
GetSubZoneText = function() return "Crusader's Chapel" end
C_Map.GetBestMapForUnit = function() return 305 end
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
fire("ENCOUNTER_END", 450, "High Inquisitor Whitemane", 1, 5, 1)
assert(DungeonMapsCharDB.runs.sm_cathedral.killed[2], "exact name wins over shared encounter ID")
assert(not DungeonMapsCharDB.runs.sm_cathedral.killed[1], "shared ID must not select Mograine first")
UnitName = function(u) if u == "boss1" then return "Only one visible unit" end return originalUnitName(u) end
fire("ENCOUNTER_START", 450, "High Inquisitor Whitemane")
assert(not DungeonMapsDB.bossNames["enUS:450"], "shared encounter must not rename individual pins")
UnitName = originalUnitName
print("OK boss aliases, live creature labels, and shared-encounter identity")

-- A hand-selected map wing can differ from the detected current wing. The map
-- button clears the displayed one; the Options button clears the current one.
C_Map.GetBestMapForUnit = function() return 304 end
GetSubZoneText = function() return "" end
local armory = {t = time(), killed = {[1] = true}}
DungeonMapsCharDB.runs.sm_armory = armory
local mapReset = DungeonMapsFrame.settings.resetBosses
rawget(mapReset, "_scripts").OnClick(mapReset)
assert(not DungeonMapsCharDB.runs.sm_cathedral, "button did not use the displayed wing")
assert(DungeonMapsCharDB.runs.sm_armory == armory, "map button cleared the detected wing instead")
local optionsReset = assert(rawget(ns.settingsPanel, "resetBosses"))
rawget(optionsReset, "_scripts").OnClick(optionsReset)
assert(not DungeonMapsCharDB.runs.sm_armory, "Options button did not clear current dungeon")
local isInInstance = IsInInstance
IsInInstance = function() return false, "none" end
DungeonMapsCharDB.runs.sm_armory = armory
rawget(optionsReset, "_scripts").OnClick(optionsReset)
assert(DungeonMapsCharDB.runs.sm_armory == armory, "Options button cleared progress outside a dungeon")
IsInInstance = isInInstance
print("OK map/Options reset target the correct wing; outside click preserves saved runs")

-- Run progress belongs to a visit, rather than the last three hours. Exercise
-- every dungeon (including shared-instance wings) through the real event handler.
local inside, dead = false, false
IsInInstance = function() return inside, inside and "party" or "none" end
UnitIsDeadOrGhost = function(u) return u == "player" and dead end
GetSubZoneText = function() return "" end
for _, d in ipairs(ns.Dungeons) do
  GetInstanceInfo = function() return d.name, "party", 1, "", 5, 0, false, d.instanceID end
  C_Map.GetBestMapForUnit = function() return d.floors[1] end
  fire("PLAYER_LEAVING_WORLD")
  inside = false; fire("PLAYER_ENTERING_WORLD", false, false)
  for _, wing in ipairs(ns.Dungeons) do
    if wing.instanceID == d.instanceID then
      DungeonMapsCharDB.runs[wing.key] = {t = time(), killed = {[1] = true}}
    end
  end
  DungeonMapsCharDB.runs.unrelated = {t = time(), killed = {[1] = true}}
  fire("PLAYER_LEAVING_WORLD")
  inside = true; fire("PLAYER_ENTERING_WORLD", false, false)
  for _, wing in ipairs(ns.Dungeons) do
    if wing.instanceID == d.instanceID then
      assert(not DungeonMapsCharDB.runs[wing.key], "fresh entry retained kills: " .. wing.key)
    end
  end
  assert(DungeonMapsCharDB.runs.unrelated.killed[1], "entry cleared another instance")
  local progress = {t = time(), killed = {[1] = true}}
  DungeonMapsCharDB.runs[d.key] = progress
  fire("ZONE_CHANGED_NEW_AREA")
  fire("PLAYER_ENTERING_WORLD", false, false) -- duplicate notification inside
  assert(DungeonMapsCharDB.runs[d.key] == progress, "duplicate event erased progress")
  fire("PLAYER_ENTERING_WORLD", false, true)
  assert(DungeonMapsCharDB.runs[d.key] == progress, "UI reload erased progress")
  fire("PLAYER_ENTERING_WORLD", true, false)
  assert(DungeonMapsCharDB.runs[d.key] == progress, "login erased progress")
  dead = true; fire("PLAYER_LEAVING_WORLD")
  inside = false; fire("PLAYER_ENTERING_WORLD", false, false)
  fire("PLAYER_LEAVING_WORLD")
  inside, dead = true, false -- automatically resurrected at the instance door
  fire("PLAYER_ENTERING_WORLD", false, false)
  assert(DungeonMapsCharDB.runs[d.key] == progress, "corpse run erased progress")
  -- Login/reload flags must also protect progress without a prior inside event,
  -- which is how a newly loaded copy of the addon starts.
  fire("PLAYER_LEAVING_WORLD")
  inside = false; fire("PLAYER_ENTERING_WORLD", false, false)
  inside = true; fire("PLAYER_ENTERING_WORLD", true, false)
  assert(DungeonMapsCharDB.runs[d.key] == progress, "login inside erased saved progress")
  inside = false; fire("PLAYER_ENTERING_WORLD", false, false)
  inside = true; fire("PLAYER_ENTERING_WORLD", false, true)
  assert(DungeonMapsCharDB.runs[d.key] == progress, "reload inside erased saved progress")
  fire("PLAYER_LEAVING_WORLD")
  inside = false; fire("PLAYER_ENTERING_WORLD", false, false)
  fire("PLAYER_LEAVING_WORLD")
  inside = true; fire("PLAYER_ENTERING_WORLD", false, false)
  assert(not DungeonMapsCharDB.runs[d.key], "living return retained kills: " .. d.key)
end
-- A missed reset is also caught by pulling a boss previously marked killed.
GetInstanceInfo = function() return "Ruins of Lordaeron", "party", 1, "", 5, 0, false, 2999 end
C_Map.GetBestMapForUnit = function() return 1029991 end
DungeonMapsFrame:Hide(); DungeonMaps_Toggle()
fire("BOSS_KILL", 3355, "The Butcher")
assert(DungeonMapsFrame.bosses[2].tipLines[1]:find("defeated"), "missing defeated label")
fire("PLAYER_LEAVING_WORLD")
inside = false; fire("PLAYER_ENTERING_WORLD", false, false)
fire("PLAYER_LEAVING_WORLD")
inside = true; fire("PLAYER_ENTERING_WORLD", false, false)
DungeonMaps_Toggle()
assert(not DungeonMapsFrame.bosses[2].tipLines[1]:find("defeated"), "stale defeated label after entry")
fire("BOSS_KILL", 3355, "The Butcher")
fire("ENCOUNTER_START", 3355, "The Butcher")
assert(not DungeonMapsCharDB.runs.ruinsoflordaeron, "living boss retained previous run's kills")
assert(not DungeonMapsFrame.bosses[2].tipLines[1]:find("defeated"), "boss restart did not redraw skull")
fire("ENCOUNTER_END", 3355, "The Butcher", 1, 5, 0)
assert(not DungeonMapsCharDB.runs.ruinsoflordaeron, "wipe counted as a kill")
fire("BOSS_KILL", 3355, "The Butcher")
fire("CHAT_MSG_SYSTEM", "Ruins of Lordaeron has been reset.")
assert(not DungeonMapsCharDB.runs.ruinsoflordaeron, "instance reset retained kills")
assert(not DungeonMapsFrame.bosses[2].tipLines[1]:find("defeated"), "reset did not redraw skull")
print("OK all dungeon runs reset; reload, login, duplicate zone events and corpse returns preserve progress")
print("OK no runtime errors")
