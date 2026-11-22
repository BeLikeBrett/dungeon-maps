-- Wailing Caverns' uninstanced approach. It is a native map only: never send
-- this context through the dungeon tracker or mix its marks with floor 279.
local _, ns = ...
ns.WailingApproach = {
	key = "wailingcaverns_approach", name = "Wailing Caverns - Approach cave",
	floors = { -43 }, approach = true,
}
ns.Floors[-43] = {
	name = "Cave entrance to instance portal",
	image = { file = "maps\\wailing_caverns_approach", square = true },
	credit = "Map: Atlas / Arith (GPL-2.0); see LICENSE-Atlas.txt",
}

-- Atlas art pixels from outdoor continent yards (north, west). Registered
-- against the client's WailingCaverns.wmo geometry: 421 texture correspondences,
-- 0.901px RMS. Only these geometric coefficients are retained; no third-party
-- renderer or restricted artwork is bundled. See validation/dungeons/wailingcaverns.
local F = { 0.129652640762, -1.152091374625, -2178.501851566,
           -1.152091374626, -0.129652640761, -805.832165823 }
local function finite(n)
	if issecretvalue and issecretvalue(n) then return false end
	return type(n) == "number" and n == n and n > -math.huge and n < math.huge
end

function ns.ApproachWorldToPixel(n, w)
	if not finite(n) or not finite(w) then return end
	local x, y = F[1]*n + F[2]*w + F[3], F[4]*n + F[5]*w + F[6]
	if x >= 0 and x <= 512 and y >= 0 and y <= 512 then return x, y end
end

local function mapWorld()
	local p = C_Map.GetPlayerMapPosition(1413, "player") -- The Barrens, in continent yards
	if not p or (issecretvalue and issecretvalue(p)) then return end
	local continent, position = C_Map.GetWorldPosFromMapPos(1413, p)
	if not finite(continent) or continent ~= 1 or not position then return end
	if issecretvalue and issecretvalue(position) then return end
	return position:GetXY()
end

local function outdoorWorld()
	local ok, inside = pcall(IsInInstance)
	if not ok or (issecretvalue and issecretvalue(inside)) or inside ~= false then return end
	if UnitPosition then
		local good, n, w, _, continent = pcall(UnitPosition, "player")
		if good and finite(continent) and continent == 1 and finite(n) and finite(w) then return n, w end
	end
	if not (C_Map and C_Map.GetPlayerMapPosition and C_Map.GetWorldPosFromMapPos) then return end
	local good, n, w = pcall(mapWorld)
	if good and finite(n) and finite(w) then return n, w end
end

function ns.ApproachPosition()
	local n, w = outdoorWorld()
	local x, y = ns.ApproachWorldToPixel(n, w)
	if not x then return end
	local rotation = 0
	if GetPlayerFacing then
		local ok, facing = pcall(GetPlayerFacing)
		if ok and finite(facing) then
			local a, b = math.cos(facing), math.sin(facing)
			rotation = math.atan2(-(F[1]*a + F[2]*b), -(F[4]*a + F[5]*b))
		end
	end
	return x, y, rotation
end
