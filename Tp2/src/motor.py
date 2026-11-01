"""Motor de tareas: cola asyncio, pool de workers, cancelación, timeouts y volcado."""
import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

from . import config

log = logging.getLogger("tareas")

ESTADOS = ("pendiente", "ejecutando", "completada", "fallida", "cancelada")
TERMINALES = ("completada", "fallida", "cancelada")

# El hash se calcula en tandas: así una cancelación o un timeout se nota entre
# tandas y el proceso hijo no sigue calculando "para nadie" durante minutos.
TANDA_HASH = 100_000


class ApagadoError(Exception):
    """El servidor se está apagando y no acepta tareas nuevas."""


class ColaLlenaError(Exception):
    """La cola alcanzó QUEUE_MAXSIZE."""


# ---------------------------------------------------------------- CPU-bound
# Funciones a nivel de módulo: el ProcessPoolExecutor las tiene que poder
# serializar (pickle) para mandarlas al proceso hijo.
def hash_tanda(dato: bytes, iteraciones: int) -> bytes:
    for _ in range(iteraciones):
        dato = hashlib.sha256(dato).digest()
    return dato


# ----------------------------------------------------------------- I/O-bound
async def _descargar_una(client: httpx.AsyncClient, url: str) -> dict:
    inicio = time.perf_counter()
    try:
        r = await client.get(url)
        status, tamano, error = r.status_code, len(r.content), None
    except Exception as e:  # CancelledError es BaseException: NO se captura acá
        status, tamano, error = None, 0, f"{type(e).__name__}: {e}"
    return {
        "url": url,
        "status": status,
        "bytes": tamano,
        "tiempo_s": round(time.perf_counter() - inicio, 3),
        "error": error,
    }


async def descargar(urls: list[str]) -> list[dict]:
    # Un solo cliente por tarea, cerrado por `async with` incluso si cancelan.
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT, follow_redirects=True) as client:
        return await asyncio.gather(*(_descargar_una(client, u) for u in urls))


# --------------------------------------------------------------------- Motor
class Motor:
    def __init__(self) -> None:
        self.tareas: dict[str, dict] = {}              # id -> registro (serializable)
        self.cola: asyncio.Queue[str] = asyncio.Queue(maxsize=config.QUEUE_MAXSIZE)
        self.jobs: dict[str, asyncio.Task] = {}        # id -> asyncio.Task del TRABAJO
        self._terminadas: dict[str, asyncio.Event] = {}
        self.ocupados: set[int] = set()
        self.workers: list[asyncio.Task] = []
        self.pool: ProcessPoolExecutor | None = None
        self.aceptando = False
        self.apagando = False

    # ---- ciclo de vida
    async def iniciar(self) -> None:
        self._reportar_volcado_previo()
        if config.HASH_MODE == "executor":
            self.pool = ProcessPoolExecutor(max_workers=config.POOL_PROCESSES)
        else:
            log.warning("HASH_MODE=%s: hashear BLOQUEARÁ el event loop (solo para medir)",
                        config.HASH_MODE)
        self.workers = [asyncio.create_task(self._worker(i), name=f"worker-{i}")
                        for i in range(config.WORKERS)]
        self.aceptando = True
        log.info("Motor iniciado: %d workers, %d procesos de pool, cola máx %d",
                 config.WORKERS, config.POOL_PROCESSES, config.QUEUE_MAXSIZE)

    async def detener(self) -> None:
        log.info("Apagado ordenado: dejo de aceptar tareas nuevas")
        self.aceptando = False
        self.apagando = True  # los workers ya no sacan tareas de la cola

        # 1) esperar (con límite) a las tareas en curso
        if not await self._esperar_ocupados(config.SHUTDOWN_GRACE):
            # 2) se acabó el tiempo: cancelar lo que siga corriendo
            for tid, job in list(self.jobs.items()):
                self.tareas[tid]["error"] = "Cancelada por apagado del servidor"
                job.cancel()
            await self._esperar_ocupados(5.0)

        # 3) recién ahora, matar a los workers (ya están ociosos en cola.get())
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

        # 4) cerrar el pool sin bloquear el loop y volcar el estado
        if self.pool:
            await asyncio.to_thread(self.pool.shutdown, wait=True, cancel_futures=True)
        self._volcar()

    async def _esperar_ocupados(self, limite: float) -> bool:
        fin = time.monotonic() + limite
        while self.ocupados and time.monotonic() < fin:
            await asyncio.sleep(0.05)
        return not self.ocupados

    # ---- API del motor
    def encolar(self, tipo: str, parametros: dict, timeout: float) -> dict:
        if not self.aceptando:
            raise ApagadoError()
        tid = str(uuid.uuid4())
        t = {
            "id": tid, "tipo": tipo, "estado": "pendiente",
            "parametros": parametros, "timeout": timeout,
            "resultado": None, "error": None,
            "creada": time.time(), "inicio": None, "fin": None,
            "duracion_s": None, "worker": None,
        }
        try:
            self.cola.put_nowait(tid)       # nunca bloquea: o entra o falla
        except asyncio.QueueFull:
            raise ColaLlenaError() from None
        self.tareas[tid] = t
        self._terminadas[tid] = asyncio.Event()
        return t

    async def cancelar(self, tid: str) -> tuple[dict, str]:
        t = self.tareas[tid]  # KeyError -> 404 en la API
        if t["estado"] in TERMINALES:
            return t, f"La tarea ya estaba {t['estado']}"

        if t["estado"] == "pendiente":
            # Sigue físicamente en la cola; el worker la descarta al sacarla.
            t["estado"] = "cancelada"
            t["error"] = "Cancelada antes de ejecutarse"
            t["fin"] = time.time()
            self._terminadas.pop(tid, None)
            return t, "Tarea cancelada antes de ejecutarse"

        # ejecutando: cancelamos el TRABAJO, no al worker
        evento = self._terminadas.get(tid)
        self.jobs[tid].cancel()
        if evento:
            try:
                await asyncio.wait_for(evento.wait(), timeout=5)
            except TimeoutError:
                return t, "Cancelación solicitada (todavía finalizando)"
        return t, "Tarea en ejecución cancelada"

    def estadisticas(self) -> dict:
        totales = dict.fromkeys(ESTADOS, 0)
        esperas: list[float] = []
        ejecuciones: dict[str, list[float]] = defaultdict(list)
        for t in self.tareas.values():
            totales[t["estado"]] += 1
            if t["inicio"]:
                esperas.append(t["inicio"] - t["creada"])
            if t["estado"] == "completada":
                ejecuciones[t["tipo"]].append(t["duracion_s"])
        todas = [d for lst in ejecuciones.values() for d in lst]
        return {
            "totales_por_estado": totales,
            "workers_total": config.WORKERS,
            "workers_ocupados": len(self.ocupados),
            "en_cola": totales["pendiente"],
            "tiempo_promedio_espera_s": _prom(esperas),
            "tiempo_promedio_ejecucion_s": _prom(todas),
            "tiempo_promedio_ejecucion_por_tipo_s": {k: _prom(v) for k, v in ejecuciones.items()},
        }

    # ---- internos
    async def _worker(self, wid: int) -> None:
        while True:
            tid = await self.cola.get()           # única cancelación "normal" de un worker
            try:
                if self.apagando:
                    continue                      # queda pendiente y se vuelca así
                t = self.tareas[tid]
                if t["estado"] != "pendiente":    # cancelada mientras esperaba en la cola
                    continue
                self.ocupados.add(wid)
                try:
                    await self._ejecutar(t, wid)
                finally:
                    self.ocupados.discard(wid)
            except asyncio.CancelledError:
                raise
            except Exception:                     # red de seguridad: el worker NO muere
                log.exception("Worker %d: error inesperado con la tarea %s", wid, tid)
            finally:
                self.cola.task_done()

    async def _ejecutar(self, t: dict, wid: int) -> None:
        tid = t["id"]
        t.update(estado="ejecutando", inicio=time.time(), worker=wid)
        t0 = time.perf_counter()
        log.info("Worker %d: ejecuta %s (%s)", wid, tid[:8], t["tipo"])

        # El trabajo corre en SU PROPIA asyncio.Task: así se lo puede cancelar
        # sin tocar al worker que lo está esperando.
        job = asyncio.create_task(self._logica(t), name=f"job-{tid[:8]}")
        self.jobs[tid] = job
        try:
            t["resultado"] = await asyncio.wait_for(job, timeout=t["timeout"])
            t["estado"] = "completada"
        except TimeoutError:
            t["estado"] = "fallida"
            t["error"] = f"Timeout de {t['timeout']}s excedido"
        except asyncio.CancelledError:
            t["estado"] = "cancelada"
            t["error"] = t["error"] or "Cancelada por el usuario"
            # ¿Cancelaron al job (DELETE) o al propio worker (apagado)?
            if asyncio.current_task().cancelling():
                raise
        except Exception as e:
            t["estado"] = "fallida"
            t["error"] = f"{type(e).__name__}: {e}"
            log.warning("Tarea %s falló: %s", tid[:8], t["error"])
        finally:
            t["fin"] = time.time()
            t["duracion_s"] = round(time.perf_counter() - t0, 3)
            self.jobs.pop(tid, None)
            ev = self._terminadas.pop(tid, None)
            if ev:
                ev.set()
            log.info("Worker %d: %s -> %s (%.2fs)", wid, tid[:8], t["estado"], t["duracion_s"])

    async def _logica(self, t: dict):
        p = t["parametros"]
        if t["tipo"] == "esperar":
            await asyncio.sleep(p["tiempo"])      # asyncio.sleep: cede el control al loop
            return {"dormido_s": p["tiempo"]}
        if t["tipo"] == "descargar":
            return await descargar(p["urls"])
        if t["tipo"] == "hashear":
            return await self._hashear(p["texto"], p["iteraciones"])
        raise ValueError(f"Tipo desconocido: {t['tipo']}")

    async def _hashear(self, texto: str, iteraciones: int) -> dict:
        dato = texto.encode()
        if self.pool is None:
            # MODO BLOQUEANTE (solo medición 2): el event loop queda congelado.
            return {"hash": hash_tanda(dato, iteraciones).hex(), "iteraciones": iteraciones}
        loop = asyncio.get_running_loop()
        restantes = iteraciones
        while restantes > 0:
            n = min(TANDA_HASH, restantes)
            dato = await loop.run_in_executor(self.pool, hash_tanda, dato, n)
            restantes -= n
        return {"hash": dato.hex(), "iteraciones": iteraciones}

    # ---- persistencia
    def _volcar(self) -> None:
        carpeta = Path(config.DUMP_DIR)
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            ruta = carpeta / f"estado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"generado": datetime.now().isoformat(),
                           "tareas": list(self.tareas.values())},
                          f, indent=2, ensure_ascii=False)
            log.info("Estado volcado en %s (%d tareas)", ruta, len(self.tareas))
        except OSError:
            log.exception("No se pudo volcar el estado")

    @staticmethod
    def _reportar_volcado_previo() -> None:
        archivos = sorted(Path(config.DUMP_DIR).glob("estado_*.json"))
        if not archivos:
            log.info("No hay volcados previos en %s", config.DUMP_DIR)
            return
        ultimo = archivos[-1]
        try:
            tareas = json.loads(ultimo.read_text(encoding="utf-8"))["tareas"]
            conteo: dict[str, int] = defaultdict(int)
            for t in tareas:
                conteo[t["estado"]] += 1
            log.info("Volcado previo encontrado: %s (%d tareas: %s)",
                     ultimo.name, len(tareas), dict(conteo))
        except (OSError, ValueError, KeyError):
            log.warning("Volcado previo ilegible: %s", ultimo.name)


def _prom(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 3) if valores else None
