"""Medición 3: techo del pool. Sube la cantidad de tareas hasta que se degrade.

Lanza N tareas `esperar` de D segundos y compara el tiempo real con el ideal
(ceil(N / WORKERS) * D). Repetí cambiando WORKERS y QUEUE_MAXSIZE:
    WORKERS=3  docker compose up --build
    WORKERS=50 docker compose up --build
"""
import argparse
import math
import statistics
import time

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--dur", type=float, default=1.0, help="segundos que dura cada tarea")
ap.add_argument("--ns", type=int, nargs="+", default=[10, 50, 100, 500, 1000, 1500, 3000])
args = ap.parse_args()

s = requests.Session()
cerradas = lambda t: t["completada"] + t["fallida"] + t["cancelada"]
workers = s.get(f"{args.api}/estadisticas").json()["workers_total"]
print(f"WORKERS={workers}  duración por tarea={args.dur}s\n")
print(f"{'N':>6} {'aceptadas':>9} {'rechaz.':>7} {'POST ms':>8} {'total s':>8} {'ideal s':>8} {'eficiencia':>10} {'tareas/s':>9} {'GET p95 ms':>10}")

for n in args.ns:
    antes = cerradas(s.get(f"{args.api}/estadisticas").json()["totales_por_estado"])
    aceptadas = rechazadas = 0
    posts = []
    t0 = time.perf_counter()
    for _ in range(n):
        p0 = time.perf_counter()
        r = s.post(f"{args.api}/tareas", json={"tipo": "esperar", "tiempo": args.dur, "timeout": 600})
        posts.append((time.perf_counter() - p0) * 1000)
        if r.status_code == 202:
            aceptadas += 1
        else:
            rechazadas += 1
    gets = []
    while True:
        g0 = time.perf_counter()
        est = s.get(f"{args.api}/estadisticas").json()
        gets.append((time.perf_counter() - g0) * 1000)
        if cerradas(est["totales_por_estado"]) - antes >= aceptadas:
            break
        time.sleep(0.1)
    total = time.perf_counter() - t0
    ideal = math.ceil(aceptadas / workers) * args.dur
    gets.sort()
    p95 = gets[max(int(len(gets) * 0.95) - 1, 0)]
    print(f"{n:>6} {aceptadas:>9} {rechazadas:>7} {statistics.mean(posts):>8.1f} {total:>8.2f} "
          f"{ideal:>8.2f} {ideal/total:>9.0%} {aceptadas/total:>9.1f} {p95:>10.1f}")
