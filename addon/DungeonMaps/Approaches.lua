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
