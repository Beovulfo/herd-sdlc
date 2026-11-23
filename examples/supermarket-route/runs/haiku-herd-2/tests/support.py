"""Shared helpers for the route tests."""

from route_optimizer import generate_map, load_store, random_items


def sample_case(kind, seed, width, height, n_items, n_products=60):
    data = generate_map(seed, width, height, kind, n_products)
    return data, load_store(data), random_items(data, seed, n_items)


def _adjacent(store, a, b):
    ax, ay = a % store.width, a // store.width
    bx, by = b % store.width, b // store.width
    return abs(ax - bx) + abs(ay - by) == 1


def assert_valid_route(tc, store, plan, items):
    """The walk starts and ends at the counter, never enters a shelf, and picks every item once."""
    pos = store.start
    picked = []
    moves = 0
    for step in plan.steps:
        if step.kind == "move":
            tc.assertTrue(store.open[step.cell], "route walks onto a blocked cell")
            tc.assertTrue(_adjacent(store, pos, step.cell), "route jumps between cells")
            pos = step.cell
            moves += 1
        else:
            tc.assertEqual(step.cell, pos, "pick happens away from the picker")
            product = store.products[step.item]
            tc.assertTrue(_adjacent(store, pos, product.y * store.width + product.x), "pick is not next to its shelf")
            picked.append(step.item)
    tc.assertEqual(pos, store.start, "route does not end at the counter")
    tc.assertEqual(plan.order, picked)
    tc.assertEqual(sorted(picked), sorted(pid for pid, _ in items))
    tc.assertEqual(moves, plan.distance_m)
