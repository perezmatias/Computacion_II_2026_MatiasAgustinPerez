"""Medición 1: 20 descargas secuenciales vs 20 concurrentes.

Uso (con `docker compose up --build` corriendo):
    python mediciones/medicion_io.py
La URL se resuelve DENTRO del contenedor de la API, por eso el host es `mock`.
"""
import argparse
import time

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--url", default="http://mock:9000/delay/2", help="URL con demora (vista desde la API)")
ap.add_argument("--n", type=int, default=20)
args = ap.parse_args()

TERMINALES = {"completada", "fallida", "cancelada"}
s = requests.Session()


def lanzar(urls):
    r = s.post(f"{args.api}/tareas", json={"tipo": "descargar", "urls": urls})
    r.raise_for_status()
    return r.json()["id"]


def esperar(tid):
    while True:
        t = s.get(f"{args.api}/tareas/{tid}").json()
        if t["estado"] in TERMINALES:
            return t
        time.sleep(0.02)  # polling fino: no infla la medición


def errores(t):
    """Cantidad de descargas que no dieron 200 (para no medir resultados contaminados)."""
    if t["estado"] != "completada":
        return len(t["parametros"]["urls"])
    return sum(1 for r in t["resultado"] if r["error"] or r["status"] != 200)


urls = [args.url] * args.n

print(f"== SECUENCIAL: {args.n} descargas, una después de otra ==")
t0 = time.perf_counter()
fallos = 0
for _ in range(args.n):
    t = esperar(lanzar([args.url]))
    fallos += errores(t)
seq = time.perf_counter() - t0
print(f"Tiempo secuencial: {seq:.2f} s  (descargas con error: {fallos})")

print(f"\n== CONCURRENTE: {args.n} descargas en UNA tarea (asyncio.gather) ==")
t0 = time.perf_counter()
t = esperar(lanzar(urls))
con = time.perf_counter() - t0
print(f"Tiempo concurrente: {con:.2f} s  (descargas con error: {errores(t)})")

print(f"\n== {args.n} TAREAS separadas en paralelo (limitado por WORKERS) ==")
t0 = time.perf_counter()
ids = [lanzar([args.url]) for _ in range(args.n)]
for i in ids:
    esperar(i)
par = time.perf_counter() - t0
w = s.get(f"{args.api}/estadisticas").json()["workers_total"]
print(f"Tiempo con {w} workers: {par:.2f} s")

print("\n== RESULTADOS ==")
print(f"Secuencial : {seq:.2f} s")
print(f"Concurrente: {con:.2f} s   -> speedup {seq / con:.1f}x")
print(f"{args.n} tareas / {w} workers: {par:.2f} s   -> speedup {seq / par:.1f}x")
