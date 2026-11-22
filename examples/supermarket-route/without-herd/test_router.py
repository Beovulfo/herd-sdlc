"""Run: python3 test_router.py  (checks correctness + >30% time saving over several stores/lists)"""
import random
from router import Store, gen_store, optimize, simulate

# tiny hand-checkable map: corridor, item at far end -> round trip 2*5
tiny = Store({"grid": ["S.....", "######"], "products": {"A": {"name": "a", "pos": [0, 5]}}})
d, t, _ = simulate(tiny, ["A"], speed=1.0, pick=5, every=0, out=lambda *_: None)
assert (d, t) == (10, 15.0), (d, t)

q = lambda *_: None
for seed, w, h, n in [(1, 60, 40, 15), (2, 120, 80, 25), (3, 200, 120, 40), (4, 120, 80, 8)]:
    data = gen_store(w, h, seed)
    s = Store(data)
    for trial in range(3):
        ids = random.Random(seed * 10 + trial).sample(sorted(data["products"]), n)
        o = optimize(s, ids)
        assert sorted(o) == sorted(ids)  # every item visited exactly once
        t0 = simulate(s, ids, every=0, out=q)[1]
        t1 = simulate(s, o, every=0, out=q)[1]
        sv = 100 * (1 - t1 / t0)
        print(f"seed={seed} {w}x{h} n={n}: list {t0:.0f}s opt {t1:.0f}s saving {sv:.1f}%")
        assert sv > 30, sv
print("OK")
