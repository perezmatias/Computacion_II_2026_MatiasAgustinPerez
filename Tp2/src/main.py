import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

task_queue = asyncio.Queue()
WORKERS_COUNT = 3

async def worker(worker_id: int):
    while True:
        try:
            tarea = await task_queue.get()
            
            if tarea == "esperar":
                await asyncio.sleep(5)
            else:
                # TODO: Implementar descargar y hashear
                await asyncio.sleep(1)
            
            task_queue.task_done()
        except asyncio.CancelledError:
            break

@asynccontextmanager
async def lifespan(app: FastAPI):
    workers = [asyncio.create_task(worker(i)) for i in range(WORKERS_COUNT)]
    yield
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

app = FastAPI(lifespan=lifespan)

@app.post("/tareas")
async def encolar_tarea(tipo_tarea: str):
    tarea_id = "temp_id_123"
    await task_queue.put(tipo_tarea)
    return {"id": tarea_id, "estado": "pendiente"}

@app.get("/tareas")
async def listar_tareas():
    return []

@app.get("/tareas/{id}")
async def obtener_tarea(id: str):
    return {"id": id, "estado": "pendiente"}

@app.delete("/tareas/{id}")
async def cancelar_tarea(id: str):
    return {"mensaje": f"Tarea {id} cancelada (simulado)"}

@app.get("/estadisticas")
async def obtener_estadisticas():
    return {"pendientes": 0, "ejecutando": 0, "completadas": 0}

if __name__ == '__main__':
    uvicorn.run("src.main:app", host='0.0.0.0', port=8000, reload=True)