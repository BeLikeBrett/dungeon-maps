"""Hidden, soft route context. Imported guide paths are suggestions, never walls.

Sampled paths form a small graph. We favour guesses near those paths and gently
downweight moves between nearby lanes when the known connection is a long way
around. Both directions work; disconnected traces and uncharted shortcuts stay
possible. Spatial lookups and bounded graph searches are cached, not per-frame.
"""

from collections import defaultdict
import heapq
import math

import numpy as np

SPACING = 5.0          # world yards between samples
JOIN = 2.0             # only merge almost coincident trace points
LANE = 12.0            # approximate guides/art: allow room to move around
CELL = 4.0
REACH = 100.0


class RouteGraph:
    def __init__(self, data, floor, paths):
        points, edges, buckets = [], defaultdict(dict), defaultdict(list)

        def node(p):
            key = tuple(np.floor(p / JOIN).astype(int))
            for x in range(key[0] - 1, key[0] + 2):
                for y in range(key[1] - 1, key[1] + 2):
                    for i in buckets[x, y]:
                        if np.linalg.norm(points[i] - p) <= JOIN:
                            return i
            i = len(points)
            points.append(p)
            buckets[key].append(i)
            return i

        for path in paths:
            uv = np.asarray(path.get("pts", []), float).reshape(-1, 2)
            if len(uv) < 2:
                continue
            nw = np.column_stack(data.to_world(floor, uv[:, 0], uv[:, 1]))
            last = None
            for a, b in zip(nw[:-1], nw[1:]):
                for t in np.linspace(0, 1, max(2, math.ceil(np.linalg.norm(b - a) / SPACING) + 1)):
                    i = node(a + t * (b - a))
                    if last is not None and last != i:
                        d = float(np.linalg.norm(points[last] - points[i]))
                        edges[last][i] = edges[i][last] = d
                    last = i
        self.points = np.asarray(points).reshape(-1, 2)
        self.edges = edges
        self.buckets = defaultdict(list)
        for i, p in enumerate(self.points):
            self.buckets[tuple(np.floor(p / 16).astype(int))].append(i)
        self.nearest_cache, self.distance_cache = {}, {}
        self.component = np.full(len(points), -1, int)
        for i in range(len(points)):
            if self.component[i] >= 0:
                continue
            todo = [i]
            self.component[i] = i
            while todo:
                for j in edges[todo.pop()]:
                    if self.component[j] < 0:
                        self.component[j] = i
                        todo.append(j)

    def nearest(self, p):
        # Nearby particles share cells. Resolve each distinct cell once, then
        # distribute its result with NumPy instead of looping over every guess.
        cells, inverse = np.unique(np.floor(p / CELL).astype(int), axis=0, return_inverse=True)
        resolved = np.full(len(cells), -1, int)
        for k, coords in enumerate(cells):
            cell = tuple(coords)
            if cell not in self.nearest_cache:
                centre = (np.asarray(cell) + 0.5) * CELL
                bx, by = np.floor(centre / 16).astype(int)
                candidates = [i for x in range(bx - 1, bx + 2) for y in range(by - 1, by + 2)
                              for i in self.buckets[x, y]]
                best = -1
                if candidates:
                    ds = ((self.points[candidates] - centre) ** 2).sum(1)
                    best = candidates[int(np.argmin(ds))]
                self.nearest_cache[cell] = best
            resolved[k] = self.nearest_cache[cell]
        ids = resolved[inverse]
        d = np.full(len(p), math.inf)
        ok = ids >= 0
        d[ok] = np.linalg.norm(p[ok] - self.points[ids[ok]], axis=1)
        return ids, d

    def distances(self, start):
        if start not in self.distance_cache:
            ds, todo = {start: 0.0}, [(0.0, start)]
            while todo:
                d, i = heapq.heappop(todo)
                if d > ds[i]:
                    continue
                for j, length in self.edges[i].items():
                    nd = d + length
                    if nd <= REACH and nd < ds.get(j, math.inf):
                        ds[j] = nd
                        heapq.heappush(todo, (nd, j))
            self.distance_cache[start] = ds
        return self.distance_cache[start]

    def weights(self, p, previous, travelled):
        ids, d = self.nearest(p)
        # Modest preference. A room's edge, a shortcut, or an incomplete guide is legal.
        like = 0.85 + 0.15 * np.exp(-0.5 * (d / LANE) ** 2)
        if previous is not None:
            old, od = self.nearest(previous)
            valid = (ids >= 0) & (old >= 0) & (d < LANE) & (od < LANE)
            for k in np.flatnonzero(valid & (ids != old)):
                a, b = old[k], ids[k]
                if self.component[a] != self.component[b]:
                    continue  # missing connections are unknown, not impassable
                detour = self.distances(a).get(b, math.inf)
                if detour > travelled + d[k] + od[k] + 12:
                    like[k] *= 0.65
        return like, d < LANE


class Routes:
    def __init__(self, data):
        self.data, self.graphs = data, {}
        self.enabled = True

    def get(self, floor):
        if not self.enabled:
            return None
        if floor not in self.graphs:
            paths = [p for r in getattr(self.data, "routes", {}).values()
                     for p in r.get("paths", []) if p.get("floor") == floor]
            self.graphs[floor] = RouteGraph(self.data, floor, paths) if paths else None
        return self.graphs[floor]
