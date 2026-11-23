"""Supermarket map and shopping-list parsing. Standard library only."""
import json
from dataclasses import dataclass

WALKABLE = ".E"  # '.' aisle, 'E' entrance; every other grid character blocks movement


class RouteError(Exception):
    """A bad input or an unreachable product: reported as one clear message."""


@dataclass(frozen=True)
class Product:
    id: str
    short_name: str
    row: int
    col: int


@dataclass
class Store:
    grid: list
    entrance: tuple
    products: dict

    def walkable(self, row, col):
        return (0 <= row < len(self.grid) and 0 <= col < len(self.grid[row])
                and self.grid[row][col] in WALKABLE)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def parse_map(data):
    """Validate a decoded map (a dict with 'grid' and 'products') and build a Store."""
    if not isinstance(data, dict):
        raise RouteError("map must be a JSON object with 'grid' and 'products'")
    grid = data.get("grid")
    if not isinstance(grid, list) or not grid or not all(isinstance(row, str) and row for row in grid):
        raise RouteError("map 'grid' must be a non-empty list of text rows")
    if any(len(row) != len(grid[0]) for row in grid):
        raise RouteError("map 'grid' rows must all have the same length")
    entrances = [(r, c) for r, row in enumerate(grid) for c, ch in enumerate(row) if ch == "E"]
    if len(entrances) != 1:
        raise RouteError(f"map must have exactly one entrance 'E', found {len(entrances)}")
    items = data.get("products")
    if not isinstance(items, list):
        raise RouteError("map 'products' must be a list")

    store = Store(grid=grid, entrance=entrances[0], products={})
    height, width = len(grid), len(grid[0])
    for item in items:
        if not isinstance(item, dict) or not all(k in item for k in ("id", "short_name", "row", "col")):
            raise RouteError("each map product needs 'id', 'short_name', 'row' and 'col'")
        pid, name, row, col = item["id"], item["short_name"], item["row"], item["col"]
        if not isinstance(pid, str) or not pid or not isinstance(name, str):
            raise RouteError("product 'id' and 'short_name' must be text")
        if not _is_int(row) or not _is_int(col) or not (0 <= row < height and 0 <= col < width):
            raise RouteError(f"product {pid} is outside the map")
        if pid in store.products:
            raise RouteError(f"product id {pid} appears twice in the map")
        if store.walkable(row, col):
            raise RouteError(f"product {pid} sits on an aisle cell, not on a shelf")
        store.products[pid] = Product(pid, name, row, col)
    return store


def load_map(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise RouteError(f"cannot read map {path}: {getattr(e, 'strerror', None) or e}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise RouteError(f"map {path} is not valid JSON") from None
    return parse_map(data)


def parse_list(text, store):
    """Parse 'id:short name' lines into Products, in the customer's order. Duplicates are kept."""
    items = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if ":" not in line:
            raise RouteError(f"list line {number} must be 'id:short name', got {line!r}")
        pid = line.split(":", 1)[0].strip()
        if pid not in store.products:
            raise RouteError(f"list line {number}: unknown product id {pid!r}")
        items.append(store.products[pid])
    if not items:
        raise RouteError("shopping list is empty")
    return items


def read_list(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise RouteError(f"cannot read list {path}: {getattr(e, 'strerror', None) or e}") from None
