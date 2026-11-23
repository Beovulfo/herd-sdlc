# Route optimizer

    python3 route.py demo [--aisles 20 --length 60 --items 40 --seed 1]
    python3 route.py gen map.json list.txt   # sample inputs
    python3 route.py run map.json list.txt --live 25   # step-by-step KPIs, then comparison
    python3 -m unittest

Map JSON: grid rows (# blocked/shelf, . walkable, S start, E exit) + products [{id,name,x,y}]; list file: one id:name per line.
Algorithm: BFS distances on the grid, nearest-neighbour + 2-opt + or-opt, exact pickup-side choice by DP. Baseline uses the same exact pathing in list order. Speed 1.2 m/s and 5 s/pick are constants in route.py.
