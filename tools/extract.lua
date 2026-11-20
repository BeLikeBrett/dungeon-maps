-- Builds the Dungeon Maps addon's Data.lua from Forever Dungeon Routes' generated data (MIT).
-- usage: lua5.1 extract.lua <FDR dir> <addon Data.lua out> <tracker JSON out>
local fdr, out, jsonOut = arg[1], arg[2], arg[3]
local DR = {}
for _, f in ipairs({ "Dungeons", "Floors", "DefaultRoutes", "Rooms", "Pictures", "Minimaps", "Entrances" }) do
  local chunk = assert(loadfile(fdr .. "/Data/" .. f .. ".lua"))
  setfenv(chunk, {})                 -- plain tables only: no globals reachable
  chunk("ForeverDungeonRoutes", DR)
end

local function num(n)
  if n == math.floor(n) and math.abs(n) < 1e15 then return string.format("%d", n) end
  return (string.format("%.6g", n))
end
local function ser(v, ind)
  local t = type(v)
  if t == "number" then return num(v) end
  if t == "string" then return string.format("%q", v) end
  if t == "boolean" then return tostring(v) end
  assert(t == "table", t)
  -- array part inline, map part sorted
  local parts, n = {}, #v
  for i = 1, n do parts[#parts + 1] = ser(v[i], ind) end
  local keys = {}
  for k in pairs(v) do if not (type(k) == "number" and k >= 1 and k <= n and k == math.floor(k)) then keys[#keys + 1] = k end end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  for _, k in ipairs(keys) do
    local ks = (type(k) == "string" and k:match("^[%a_][%w_]*$")) and k or ("[" .. ser(k) .. "]")
    parts[#parts + 1] = ks .. " = " .. ser(v[k], ind)
  end
  return "{ " .. table.concat(parts, ", ") .. " }"
end

local D = { Dungeons = {}, Floors = {}, MinimapArt = {}, Rooms = {}, Bosses = {}, Entry = {}, Zone = {} }
local usedFloors = {}
for _, d in ipairs(DR.Dungeons) do
  table.insert(D.Dungeons, { key = d.key, instanceID = d.instanceID, floors = d.floors, name = d.name, raid = d.raid })
  for _, f in ipairs(d.floors) do usedFloors[f] = true end
end
local noArt = {}
for f in pairs(usedFloors) do
  local info = DR.Floors[f]
  if info then
    local tiles = info.tiles and #info.tiles == 12 and info.tiles or nil
    D.Floors[f] = { name = info.name, tiles = tiles, image = info.image, credit = info.credit }
    -- minimap pictures: the fallback where a floor has neither tiles nor a drawn map
    if not tiles and not info.image then
      if DR.MinimapArt and DR.MinimapArt[f] then D.MinimapArt[f] = DR.MinimapArt[f] else noArt[#noArt + 1] = f end
    end
  else
    noArt[#noArt + 1] = f
  end
end
for key, rooms in pairs(DR.Rooms) do
  D.Rooms[key] = {}
  for _, r in ipairs(rooms) do table.insert(D.Rooms[key], { name = r.name, boxes = r.boxes }) end
end
for key, route in pairs(DR.DefaultRoutes) do
  local bosses = {}
  for _, s in ipairs(route.stops or {}) do
    if s.kind == "boss" and s.floor and s.x and s.y then
      table.insert(bosses, { floor = s.floor, x = s.x, y = s.y, name = s.name, encounters = s.encounters, note = s.note })
    end
  end
  if #bosses > 0 then D.Bosses[key] = bosses end
  for _, p in ipairs(route.paths or {}) do
    if p.kind == "main" and p.pts and p.pts[2] then D.Entry[key] = { floor = p.floor, x = p.pts[1], y = p.pts[2] } break end
  end
end
for key, e in pairs(DR.Entrances or {}) do D.Zone[key] = { map = e.map, x = e.x, y = e.y } end

-- tracker data (JSON): the same dungeon order as Data.lua (the beacon sends 1-based indexes into it),
-- each floor's place in the world (world = { minX, minY, maxX, maxY }, x north / y west, yards; frame =
-- the turned drawn maps' map point u = a*N + b*W + c, v = d*N + e*W + f) and the room boxes.
local function json(v)
  local t = type(v)
  if t == "number" then return num(v) end
  if t == "string" then return (string.format("%q", v):gsub("\\\n", "\\n")) end
  if t == "boolean" then return tostring(v) end
  if t == "nil" then return "null" end
  local n = #v
  local isArray = n > 0 or next(v) == nil
  if isArray then
    for k in pairs(v) do if type(k) ~= "number" then isArray = false break end end
  end
  local parts = {}
  if isArray then
    for i = 1, n do parts[#parts + 1] = json(v[i]) end
    return "[" .. table.concat(parts, ",") .. "]"
  end
  local keys = {}
  for k in pairs(v) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  for _, k in ipairs(keys) do parts[#parts + 1] = string.format("%q", tostring(k)) .. ":" .. json(v[k]) end
  return "{" .. table.concat(parts, ",") .. "}"
end
if jsonOut then
  local T = { dungeons = {}, floors = {}, rooms = {} }
  for _, d in ipairs(DR.Dungeons) do table.insert(T.dungeons, { key = d.key, name = d.name, floors = d.floors }) end
  for f in pairs(usedFloors) do
    local info = DR.Floors[f]
    if info then T.floors[tostring(f)] = { name = info.name, world = info.world, frame = info.frame } end
  end
  T.bosses, T.entry = {}, {}
  for key, list in pairs(D.Bosses) do
    T.bosses[key] = {}
    for _, b in ipairs(list) do table.insert(T.bosses[key], { floor = b.floor, x = b.x, y = b.y, name = b.name }) end
  end
  for key, e in pairs(D.Entry) do T.entry[key] = { floor = e.floor, x = e.x, y = e.y } end
  for key, rooms in pairs(D.Rooms) do
    T.rooms[key] = {}
    for _, r in ipairs(rooms) do table.insert(T.rooms[key], { name = r.name, boxes = r.boxes }) end
  end
  local jh = assert(io.open(jsonOut, "w"))
  jh:write(json(T), "\n")
  jh:close()
end

local fh = assert(io.open(out, "w"))
fh:write([[
-- Dungeon Maps data. GENERATED by extract.lua from Forever Dungeon Routes 1.3.6 (MIT License,
-- Copyright (c) 2026 Checkov23 - see LICENSE-ForeverDungeonRoutes.txt), which generated it from the
-- WoW: Forever client's own tables. Classic floors use the game's own map tiles (file IDs); the new
-- Forever dungeons use the bundled Santiago Reyes maps (maps/, see maps/CREDITS.txt for the separate
-- artist credits), else the game's minimap pictures (file IDs). Do not edit by hand.
local _, ns = ...
]])
for _, name in ipairs({ "Dungeons", "Floors", "MinimapArt", "Rooms", "Bosses", "Entry", "Zone" }) do
  local t = D[name]
  if name == "Dungeons" then
    fh:write("ns.Dungeons = {\n")
    for _, d in ipairs(t) do fh:write("\t", ser(d), ",\n") end
  else
    fh:write("ns.", name, " = {\n")
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do fh:write("\t[", ser(k), "] = ", ser(t[k]), ",\n") end
  end
  fh:write("}\n")
end
fh:close()
local nb, nr = 0, 0
for _ in pairs(D.Bosses) do nb = nb + 1 end
for _ in pairs(D.Rooms) do nr = nr + 1 end
print(("dungeons %d, floors %d, minimap-art floors %d, dungeons with rooms %d, with bosses %d; floors with no art: %s"):format(
  #D.Dungeons, (function() local c = 0 for _ in pairs(D.Floors) do c = c + 1 end return c end)(),
  (function() local c = 0 for _ in pairs(D.MinimapArt) do c = c + 1 end return c end)(), nr, nb, table.concat(noArt, ",")))
