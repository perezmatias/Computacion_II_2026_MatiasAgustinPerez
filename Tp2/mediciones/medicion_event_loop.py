"""Medición 2: ¿cuánto tarda GET /tareas mientras corre una tarea CPU-bound?

Hay que correrla DOS veces, reiniciando la API entre una y otra:
    HASH_MODE=bloqueante docker compose up --build   ->  python mediciones/medicion_event_loop.py --etiqueta SIN_EXECUTOR
    HASH_MODE=executor   docker compose up --build   ->  python mediciones/medicion_event_loop.py --etiqueta CON_EXECUTOR
"""
import argparse
import statistics
import threading
import time

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--iteraciones", type=int, default=5_000_000)
ap.add_argument("--etiqueta", default="")
args = ap.parse_args()

latencias: list[float] = []
fallos = 0
parar = threading.Event()


def sondear():
    global fallos
    s = requests.Session()
    while not parar.is_set():
        t0 = time.perf_counter()
        try:
            s.get(f"{args.api}/tareas", timeout=120)
            latencias.append(time.perf_counter() - t0)
        except requests.RequestException:
            fallos += 1
        time.sleep(0.05)


s = requests.Session()
# Línea base con el servidor ocioso
base = []
for _ in range(20):
    t0 = time.perf_counter()
    s.get(f"{args.api}/tareas")
    base.append(time.perf_counter() - t0)
print(f"[{args.etiqueta}] Latencia base (ocioso): media {statistics.mean(base)*1000:.1f} ms")

hilo = threading.Thread(target=sondear, daemon=True)
hilo.start()
time.sleep(0.3)

t0 = time.perf_counter()
tid = s.post(f"{args.api}/tareas", json={
    "tipo": "hashear", "texto": "medicion", "iteraciones": args.iteraciones, "timeout": 600
}).json()["id"]
while s.get(f"{args.api}/tareas/{tid}", timeout=120).json()["estado"] in ("pendiente", "ejecutando"):
    time.sleep(0.1)
total = time.perf_counter() - t0
parar.set()
hilo.join()

ms = sorted(x * 1000 for x in latencias)
print(f"[{args.etiqueta}] Duración de la tarea hashear ({args.iteraciones:,} it.): {total:.2f} s")
print(f"[{args.etiqueta}] GET /tareas durante la tarea: {len(ms)} respuestas, {fallos} fallidas")
if ms:
    print(f"[{args.etiqueta}]   media {statistics.mean(ms):.1f} ms | mediana {statistics.median(ms):.1f} ms"
          f" | p95 {ms[int(len(ms)*0.95)-1]:.1f} ms | MÁXIMA {ms[-1]:.1f} ms")
