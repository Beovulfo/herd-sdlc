"""Command line: python3 -m optimizer run|compare MAP LIST."""
import argparse
import sys
import time

from optimizer.plan import list_order_route, optimized_route
from optimizer.simulate import compare, run
from optimizer.store import StoreError, load_list, load_store


def main(argv=None):
    parser = argparse.ArgumentParser(prog="optimizer", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="simulate one route step by step")
    p_run.add_argument("map")
    p_run.add_argument("list")
    p_run.add_argument("--route", choices=["list", "optimized"], default="optimized")
    p_run.add_argument("--delay", type=float, default=0.0, help="seconds to wait per event")
    p_cmp = sub.add_parser("compare", help="list-order route against the optimized route")
    p_cmp.add_argument("map")
    p_cmp.add_argument("list")
    args = parser.parse_args(argv)
    try:
        store = load_store(args.map)
        items = load_list(args.list, store)
        if args.cmd == "run":
            order = list_order_route(items) if args.route == "list" else optimized_route(store, items)
            for e in run(store, items, order):
                print(f"{e.kind:<5} step={e.distance:>5} time_s={e.time_s:8.1f} "
                      f"picked={e.picked_count}/{len(items)} {e.picked_id or '-':<6} cell={e.cell}")
                if args.delay:
                    time.sleep(args.delay)
            return 0
        result = compare(store, items)
        for name in ("list", "optimized"):
            k = result[name]
            print(f"{name:<10} time_to_prepare_basket_s={k['time_to_prepare_basket_s']:.1f} "
                  f"distance_steps={k['distance_steps']} items_picked={k['items_picked']}")
        print(f"saving: {result['saving_pct']:.1f}% of time to prepare the basket")
        return 0
    except StoreError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
