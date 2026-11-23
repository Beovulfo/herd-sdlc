"""Load a supermarket map and a shopping list, and walk the aisle grid.

Map JSON: {"layout": ["S..#", ...], "products": [{"id", "name", "row", "col"}]}.
Layout characters: "#" wall, "." aisle, "S" the start (packing point, exactly one).
A product sits on an aisle cell where the picker stops.
Shopping list text: one "id:short name" per line. Repeated lines are repeated picks.
"""
import json
from collections import deque
from dataclasses import dataclass


class StoreError(ValueError):
    """A bad map or list. The message says what to fix."""


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    cell: tuple  # (row, col)


@dataclass(frozen=True)
class Store:
    rows: int
    cols: int
    free: tuple  # flat row-major booleans: True for aisle and start cells
    start: tuple  # (row, col)
    products: dict  # id -> Product
    broken: dict  # id -> reason, for map entries that are unusable

    def index(self, cell):
        return cell[0] * self.cols + cell[1]

    def distances(self, src):
        """Steps from flat index src to every cell; -1 where unreachable."""
        dist = [-1] * (self.rows * self.cols)
        dist[src] = 0
        queue = deque([src])
        while queue:
            i = queue.popleft()
            r, c = divmod(i, self.cols)
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    j = nr * self.cols + nc
                    if self.free[j] and dist[j] < 0:
                        dist[j] = dist[i] + 1
                        queue.append(j)
        return dist

    def path(self, a, b):
        """Shortest list of cells from cell a to cell b, both included; None if unreachable."""
        src, dst = self.index(a), self.index(b)
        parent = {src: None}
        queue = deque([src])
        while queue and dst not in parent:
            i = queue.popleft()
            r, c = divmod(i, self.cols)
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    j = nr * self.cols + nc
                    if self.free[j] and j not in parent:
                        parent[j] = i
                        queue.append(j)
        if dst not in parent:
            return None
        cells, i = [], dst
        while i is not None:
            cells.append(divmod(i, self.cols))
            i = parent[i]
        return cells[::-1]


def parse_store(data):
    if not isinstance(data, dict):
        raise StoreError("map must be a JSON object with 'layout' and 'products'")
    layout = data.get("layout")
    if not isinstance(layout, list) or not layout or not all(isinstance(row, str) for row in layout):
        raise StoreError("map 'layout' must be a non-empty list of strings")
    cols = len(layout[0])
    if cols == 0 or any(len(row) != cols for row in layout):
        raise StoreError("every map 'layout' row must have the same non-zero length")
    free, starts = [], []
    for r, row in enumerate(layout):
        for c, ch in enumerate(row):
            if ch not in "#.S":
                raise StoreError(f"unknown map character {ch!r} at row {r}, col {c}")
            if ch == "S":
                starts.append((r, c))
            free.append(ch != "#")
    if len(starts) != 1:
        raise StoreError(f"map must have exactly one 'S' start cell, found {len(starts)}")

    raw = data.get("products", [])
    if not isinstance(raw, list):
        raise StoreError("map 'products' must be a list")
    products, broken = {}, {}
    for n, p in enumerate(raw):
        try:
            product = _check_product(p, n, layout, cols)
        except StoreError as e:  # a broken product only fails if the list asks for it
            key = p.get("id") if isinstance(p, dict) and isinstance(p.get("id"), str) else f"#{n}"
            broken[key] = str(e)
            continue
        if product.id in products or product.id in broken:
            products.pop(product.id, None)
            broken[product.id] = f"duplicate product id {product.id!r} in map"
            continue
        products[product.id] = product

    return Store(len(layout), cols, tuple(free), starts[0], products, broken)


def _check_product(p, n, layout, cols):
    if not isinstance(p, dict):
        raise StoreError(f"product {n} must be an object")
    pid, name = p.get("id"), p.get("name")
    row, col = p.get("row"), p.get("col")
    if not isinstance(pid, str) or not pid:
        raise StoreError(f"product {n} needs a non-empty string 'id'")
    if not isinstance(name, str) or not name:
        raise StoreError(f"product {pid} needs a non-empty string 'name'")
    if not (isinstance(row, int) and isinstance(col, int)):
        raise StoreError(f"product {pid} needs integer 'row' and 'col'")
    if not (0 <= row < len(layout) and 0 <= col < cols):
        raise StoreError(f"product {pid} at row {row}, col {col} is outside the map")
    if layout[row][col] == "#":
        raise StoreError(f"product {pid} is on a wall cell at row {row}, col {col}")
    return Product(pid, name, (row, col))


def load_store(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise StoreError(f"cannot read map file {path}: {e.strerror}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise StoreError(f"map file {path} is not valid JSON: {e}") from None
    return parse_store(data)


def parse_list(text, store):
    """Return the requested products in list order; repeated lines are repeated picks."""
    items = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if ":" not in line:
            raise StoreError(f"list line {lineno}: expected 'id:short name', got {line.strip()!r}")
        pid = line.split(":", 1)[0].strip()
        if not pid:
            raise StoreError(f"list line {lineno}: empty product id")
        if pid in store.broken:
            raise StoreError(f"list line {lineno}: product {pid} is unusable in the map: {store.broken[pid]}")
        if pid not in store.products:
            raise StoreError(f"list line {lineno}: unknown product id {pid!r}")
        items.append(store.products[pid])
    if not items:
        raise StoreError("the shopping list is empty")
    return items


def load_list(path, store):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise StoreError(f"cannot read list file {path}: {getattr(e, 'strerror', None) or e}") from None
    return parse_list(text, store)
