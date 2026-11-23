"""Command line: plan the delivery guy's basket route and simulate it step by step."""
import argparse
import sys
import time

from supermarket_route.layout import RouteError, load_map, parse_list, read_list
from supermarket_route.planner import build_model, route
from supermarket_route.simulate import compare, kpis, simulate


def _kpi_line(label, result):
    return (f"{label:<11} time-to-prepare-basket={result['time_to_prepare_basket']:.1f} s"
            f"  distance-covered={result['distance_covered']} steps")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="supermarket_route", description=__doc__)
    parser.add_argument("--map", required=True, help="supermarket map, JSON")
    parser.add_argument("--list", required=True, dest="list_path",
                        help="shopping list, one 'id:short name' per line")
    parser.add_argument("--mode", choices=("list", "optimized", "compare"), default="compare")
    parser.add_argument("--walk-seconds", type=float, default=1.0, help="seconds per step")
    parser.add_argument("--pick-seconds", type=float, default=3.0, help="seconds per picked line")
    parser.add_argument("--trace", action="store_true", help="print every simulated step")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds to wait per step (real-time playback)")
    args = parser.parse_args(argv)

    try:
        store = load_map(args.map)
        model = build_model(store, parse_list(read_list(args.list_path), store))

        def on_step(label, step):
            if args.trace:
                print(f"  {label:<10} t={step['t']:7.1f} s  {step['event']:<5} "
                      f"at ({step['row']},{step['col']})  distance={step['distance_covered']}")
            if args.delay:
                time.sleep(args.delay)

        if args.mode == "compare":
            result = compare(model, args.walk_seconds, args.pick_seconds, on_step)
            print(_kpi_line("list-order", result["list_order"]))
            print(_kpi_line("optimized", result["optimized"]))
            print(f"saving      {result['saving_pct']:.1f}% of time-to-prepare-basket")
        else:
            steps = []
            for step in simulate(model, route(model, args.mode), args.walk_seconds, args.pick_seconds):
                on_step(args.mode, step)
                steps.append(step)
            print(_kpi_line(args.mode, kpis(steps)))
    except RouteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
