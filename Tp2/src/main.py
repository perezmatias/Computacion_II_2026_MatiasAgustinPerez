import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

task_queue = asyncio.Queue()
WORKERS_COUNT = 3

# Diccionario global para guardar el estado en memoria
tareas_db = {}

async def worker(worker_id: int):
    while True:
        try:
            # 1. Ahora sacamos un diccionario de la cola
            tarea_data = await task_queue.get()
            tarea_id = tarea_data["id"]
            tipo_tarea = tarea_data["tipo"]
            
            # 2. Actualizamos el estado a ejecutando
            tareas_db[tarea_id]["estado"] = "ejecutando"
            print(f"Worker {worker_id} ejecutando tarea {tarea_id} de tipo {tipo_tarea}")
            
            if tipo_tarea == "esperar":
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(1)
            
            # 3. Al finalizar, actualizamos a completada
            tareas_db[tarea_id]["estado"] = "completada"
            
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
    # Generamos un ID único
    tarea_id = str(uuid.uuid4())
    
    # Guardamos el estado inicial en el diccionario
    tareas_db[tarea_id] = {"estado": "pendiente"}
    
    # Encolamos el diccionario con toda la información necesaria
    await task_queue.put({"id": tarea_id, "tipo": tipo_tarea})
    
    return {"id": tarea_id, "estado": "pendiente"}

@app.get("/tareas")
async def listar_tareas():
    return tareas_db

@app.get("/tareas/{id}")
async def obtener_tarea(id: str):
    # Buscamos en el diccionario, si no existe devolvemos un mensaje de error
    return tareas_db.get(id, {"error": "Tarea no encontrada"})

@app.delete("/tareas/{id}")
async def cancelar_tarea(id: str):
    return {"mensaje": f"Tarea {id} cancelada (simulado)"}

@app.get("/estadisticas")
async def obtener_estadisticas():
    return {"pendientes": 0, "ejecutando": 0, "completadas": 0}

if __name__ == '__main__':
    uvicorn.run("src.main:app", host='0.0.0.0', port=8000, reload=True)