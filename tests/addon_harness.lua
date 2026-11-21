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
      assert(m.picture._texture == "Interface\\AddOns\\DungeonMaps\\" .. info.image.file, m.picture._texture)
      assert(m.picture._texcoord[2] == (info.image.right or 1) and m.picture._texcoord[4] == (info.image.bottom or 1))
      local file = assert(io.open(ADDONS .. "/DungeonMaps/" .. info.image.file:gsub("\\", "/") .. ".blp", "rb"))
      assert(file:read(4) == "BLP2", "invalid BLP image for floor " .. floor)
      file:close()
      pictures = pictures + 1
    end
  end
end
assert(pictures == 17, "expected all 17 bundled map pictures, got " .. pictures)
print("OK 17 bundled pictures loaded without Forever Dungeon Routes")
print("OK no runtime errors")
