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
    if k == "GetHeight" then return function(s) return rawget(s, "_h") or 1080 end end
    if k == "GetWidth" then return function(s) return rawget(s, "_w") or 1080 end end
    if k == "GetLeft" then return function(s) return rawget(s, "_l") end end
    if k == "GetTop" then return function(s) return rawget(s, "_t") end end
    if k == "GetEffectiveScale" then return function(s) return rawget(s, "_eff") or 0.75 end end
    if k == "SetColorTexture" then return function(s, r, g, b) rawset(s, "_c", { r, g, b }) end end
    if k == "SetClipsChildren" then return function(s) rawset(s, "_clips", true) end end
    if k == "GetZoom" then return function() return 3 end end
    if k == "SetText" then return function(s, v) s._text = v end end
    if k == "SetPoint" then return function(s, ...) s._pts = {...} end end
    if k == "SetAlpha" then return function(s, v) s._alpha = v end end
    if k == "CreateTexture" or k == "CreateFontString" then return function() return widget("Region") end end
    if k == "SetTexture" then return function() return true end end
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

-- screen: 2544 x 1349 physical, UI effective scale 0.75 (UIParent 1024 units high)
PHYS_W, PHYS_H = 2544, 1349
function GetPhysicalScreenSize() return PHYS_W, PHYS_H end
UIParent._h = 1024; UIParent._eff = 0.75
local K = PHYS_H / 768                         -- physical px per unit at effective scale 1
local function place(f, eff, px, py, pw, ph)   -- put a frame at physical pixels (top-left, size)
  f._eff = eff
  f._l, f._t = px / (eff * K), (PHYS_H - py) / (eff * K)
  f._w, f._h = pw / (eff * K), ph / (eff * K)
end
Minimap = widget("Frame"); Minimap._shown = true
place(Minimap, 0.9, 2290.4, 64.2, 189, 189)
function GetCVar(n) if n == "minimapZoom" then return "0" end return "0" end
C_Minimap = { GetViewRadius = function() return 60 end }
local SUB = ""
function GetSubZoneText() return SUB end

-- NO Forever Dungeon Routes: the addon must stand alone
ForeverDungeonRoutes = nil
function GetMinimapZoneText() return "" end
C_ChatInfo = { RegisterAddonMessagePrefix = function() end, SendAddonMessage = function(p, t, ch) print("SEND", p, (t:gsub("\t", " | ")), ch) end }
-- grouped with four friends: the beacon carries the group's key
function IsInGroup() return true end
function IsInRaid() return false end
local GUIDS = { player = "Player-5826-0A1B2C3D", party1 = "Player-5826-00FF0011", party2 = "Player-5826-0B00B135",
  party3 = "Player-5826-01234567", party4 = "Player-5826-0C0FFEE0" }
function UnitGUID(u) return GUIDS[u] end
DungeonMapsTestArrowSize = 1.4
function time() return os.time() end
DungeonMapsDB, DungeonMapsCharDB = nil, nil
local ns = {}
assert(loadfile(ADDONS .. "/DungeonMaps/Data.lua"))("DungeonMaps", ns)
assert(loadfile(ADDONS .. "/DungeonMaps/DungeonMaps.lua"))("DungeonMaps", ns)

WorldMapFrame = widget("Frame"); WorldMapFrame._shown = false
WorldMapFrame.SetMapID = function(self, id) print("WORLDMAP SetMapID", id) end

fire = function(ev, ...)
  for _, f in ipairs(ALLFRAMES) do local sc = rawget(f, "_scripts") if sc and sc.OnEvent and f ~= DungeonMapsFrame then sc.OnEvent(f, ev, ...) end end
end
fire("PLAYER_ENTERING_WORLD", false, false)
SUB = "Cleft of Shadow"
DungeonMaps_Toggle()
local canvas
for _, f in ipairs(ALLFRAMES) do if rawget(f, "_clips") then canvas = f end end
place(canvas, 0.8, 760.3, 300.7, 1002 * 0.8 * K, 668 * 0.8 * K)
DungeonMapsDB.arrowSize = DungeonMapsTestArrowSize
local beacon = DungeonMapsBeacon
place(beacon, 0.75, 0, 0, #beacon.cells * 2, 2)  -- the game's top-left corner
local ticker
for i, f in ipairs(ALLFRAMES) do if f == beacon then ticker = ALLFRAMES[i + 1] end end
rawget(ticker, "_scripts").OnUpdate(ticker, 5)
io.write("{\"cells\":[")
for i, t in ipairs(beacon.cells) do
  local c = t._c
  io.write(("%s[%d,%d,%d]"):format(i > 1 and "," or "", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5)))
end
io.write(("],\"beacon\":[0,0],\"minimap\":[2290.4,64.2,189,189],\"canvas\":[760.3,300.7,%.3f,%.3f],\"shown\":%s}\n"):format(1002 * 0.8 * K, 668 * 0.8 * K, tostring(beacon:IsShown())))
