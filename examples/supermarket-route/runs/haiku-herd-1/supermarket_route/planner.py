"""Access cells, distances between stops, and the stop order (list order or optimized)."""
from collections import deque
from dataclasses import dataclass

from supermarket_route.layout import RouteError

NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def search(store, source):
    """BFS over walkable cells: (steps dict, parent dict) for every cell reachable from source."""
    dist = {source: 0}
    parent = {source: None}
    queue = deque([source])
    while queue:
        cell = queue.popleft()
        for dr, dc in NEIGHBOURS:
            nxt = (cell[0] + dr, cell[1] + dc)
            if nxt not in dist and store.walkable(*nxt):
                dist[nxt] = dist[cell] + 1
                parent[nxt] = cell
                queue.append(nxt)
    return dist, parent


def path_to(parent, src, dst):
    """Cells from src (excluded) to dst (included), using a BFS parent map."""
    path = []
    cell = dst
    while cell != src:
        path.append(cell)
        cell = parent[cell]
    path.reverse()
    return path


@dataclass
class Model:
    store: object
    items: list   # Products in the customer's list order
    picks: list   # the access cell each item is picked from
    dist: list    # dist[a][b]: steps between stop a and stop b; stop 0 is the entrance, stop i is items[i-1]


def build_model(store, items):
    from_entrance, _ = search(store, store.entrance)
    picks = []
    for product in items:
        access = [(product.row + dr, product.col + dc) for dr, dc in NEIGHBOURS
                  if (product.row + dr, product.col + dc) in from_entrance]
        if not access:
            raise RouteError(f"product {product.id} ({product.short_name}) cannot be reached from the entrance")
        # One fixed access cell per product: the one nearest the entrance (ties: up, down, left, right).
        picks.append(min(access, key=lambda cell: from_entrance[cell]))
    stops = [store.entrance] + picks
    dist = []
    for cell in stops:
        from_cell, _ = search(store, cell)
        dist.append([from_cell[other] for other in stops])
    return Model(store, list(items), picks, dist)


def _length(dist, order):
    total, here = 0, 0
    for stop in order:
        total += dist[here][stop]
        here = stop
    return total


def _nearest_neighbour(dist, n):
    left = set(range(1, n + 1))
    order, here = [], 0
    while left:
        nxt = min(left, key=lambda j: (dist[here][j], j))
        order.append(nxt)
        left.remove(nxt)
        here = nxt
    return order


def _two_opt(dist, order):
    """Reverse segments of the open path (start fixed at the entrance) while that shortens it."""
    seq = [0] + order
    n = len(seq)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b, c = seq[i - 1], seq[i], seq[j]
                old, new = dist[a][b], dist[a][c]
                if j + 1 < n:
                    d = seq[j + 1]
                    old += dist[c][d]
                    new += dist[b][d]
                if new < old:
                    seq[i:j + 1] = seq[i:j + 1][::-1]
                    improved = True
    return seq[1:]


def route(model, mode):
    """Stop order as item indices 1..n. 'list' keeps the customer's order; 'optimized' never beats it by less."""
    n = len(model.items)
    listed = list(range(1, n + 1))
    if mode == "list":
        return listed
    if mode != "optimized":
        raise ValueError(f"unknown mode {mode!r}")
    candidate = _two_opt(model.dist, _nearest_neighbour(model.dist, n))
    return candidate if _length(model.dist, candidate) < _length(model.dist, listed) else listed
