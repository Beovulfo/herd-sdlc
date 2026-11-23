"""Route planning: list-order baseline and a nearest-neighbour + 2-opt closed tour.

Node 0 is the start cell; node k is items[k - 1]. A route is a list of item indices.
"""
from optimizer.store import StoreError


def distance_matrix(store, items):
    cells = [store.start] + [p.cell for p in items]
    idx = [store.index(c) for c in cells]
    from_start = store.distances(idx[0])
    for k, p in enumerate(items, 1):
        if from_start[idx[k]] < 0:
            raise StoreError(f"product {p.id} ({p.name}) cannot be reached from the start")
    rows = []
    for a in idx:
        dist = store.distances(a)
        rows.append([dist[b] for b in idx])
    return rows


def list_order_route(items):
    return list(range(len(items)))


def tour_cost(D, order):
    nodes = [0] + [k + 1 for k in order] + [0]
    return sum(D[a][b] for a, b in zip(nodes, nodes[1:]))


def optimized_route(store, items):
    D = distance_matrix(store, items)
    n = len(items)
    tour, left, cur = [0], set(range(1, n + 1)), 0
    while left:  # nearest neighbour start
        cur = min(left, key=lambda j: (D[cur][j], j))
        left.remove(cur)
        tour.append(cur)
    tour.append(0)
    improved = True
    while improved:  # 2-opt until no swap shortens the closed tour
        improved = False
        for i in range(1, len(tour) - 2):
            for j in range(i + 1, len(tour) - 1):
                a, b, c, d = tour[i - 1], tour[i], tour[j], tour[j + 1]
                if D[a][c] + D[b][d] < D[a][b] + D[c][d]:
                    tour[i:j + 1] = reversed(tour[i:j + 1])
                    improved = True
    return [k - 1 for k in tour[1:-1]]
