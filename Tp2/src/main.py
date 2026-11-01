"""API HTTP (FastAPI) de la plataforma de tareas distribuidas."""
import logging
from contextlib import asynccontextmanager
from typing import Literal, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from . import config
from .motor import ApagadoError, ColaLlenaError, Motor

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

motor = Motor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await motor.iniciar()
    yield                       # uvicorn captura SIGTERM/SIGINT y termina acá
    await motor.detener()


app = FastAPI(title="Plataforma de Tareas Distribuidas", lifespan=lifespan)

Tipo = Literal["descargar", "hashear", "esperar"]
Estado = Literal["pendiente", "ejecutando", "completada", "fallida", "cancelada"]


class TareaPayload(BaseModel):
    tipo: Tipo
    urls: list[str] = Field(default_factory=list, max_length=100)
    texto: str = ""
    iteraciones: int = Field(100_000, ge=1, le=1_000_000_000)
    tiempo: float = Field(5, ge=0, le=3600)
    timeout: float = Field(default_factory=lambda: config.DEFAULT_TIMEOUT, gt=0, le=3600)

    @model_validator(mode="after")
    def _validar_por_tipo(self):
        if self.tipo == "descargar":
            if not self.urls:
                raise ValueError("'descargar' requiere al menos una URL")
            if any(not u.startswith(("http://", "https://")) for u in self.urls):
                raise ValueError("Las URLs deben empezar con http:// o https://")
        if self.tipo == "hashear" and not self.texto:
            raise ValueError("'hashear' requiere 'texto'")
        return self


def _parametros(p: TareaPayload) -> dict:
    if p.tipo == "descargar":
        return {"urls": p.urls}
    if p.tipo == "hashear":
        return {"texto": p.texto, "iteraciones": p.iteraciones}
    return {"tiempo": p.tiempo}


@app.post("/tareas", status_code=202)
async def encolar_tarea(payload: TareaPayload):
    try:
        t = motor.encolar(payload.tipo, _parametros(payload), payload.timeout)
    except ApagadoError:
        raise HTTPException(503, "El servidor se está apagando: no acepta tareas nuevas")
    except ColaLlenaError:
        raise HTTPException(503, f"Cola llena ({config.QUEUE_MAXSIZE} tareas). Reintentá luego")
    return {"id": t["id"], "estado": t["estado"]}


@app.get("/tareas")
async def listar_tareas(estado: Optional[Estado] = Query(None, description="Filtrar por estado")):
    tareas = motor.tareas.values()
    return [t for t in tareas if estado is None or t["estado"] == estado]


@app.get("/tareas/{id}")
async def obtener_tarea(id: str):
    if id not in motor.tareas:
        raise HTTPException(404, "Tarea no encontrada")
    return motor.tareas[id]


@app.delete("/tareas/{id}")
async def cancelar_tarea(id: str):
    try:
        t, mensaje = await motor.cancelar(id)
    except KeyError:
        raise HTTPException(404, "Tarea no encontrada")
    return {"id": id, "estado": t["estado"], "mensaje": mensaje}


@app.get("/estadisticas")
async def obtener_estadisticas():
    return motor.estadisticas()


if __name__ == "__main__":
    # La guarda es obligatoria: en macOS/Windows el ProcessPoolExecutor usa
    # 'spawn' y re-importa el módulo en cada hijo. Sin reload: un proceso
    # supervisor duplicaría el pool y complicaría el manejo de SIGTERM.
    uvicorn.run(app, host="0.0.0.0", port=8000)