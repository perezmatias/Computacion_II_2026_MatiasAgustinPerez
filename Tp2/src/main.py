import asyncio
import uuid
import time
import hashlib
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import uvicorn

task_queue = asyncio.Queue()
WORKERS_COUNT = 3
tareas_db = {}
# Executor global basado en procesos para tareas CPU-bound
process_pool = ProcessPoolExecutor(max_workers=2)

class TareaPayload(BaseModel):
    tipo: str
    urls: list[str] = []
    texto: str = ""
    iteraciones: int = 100000

async def descargar_url(url: str):
    inicio = time.time()
    async with httpx.AsyncClient() as client:
        try:
            respuesta = await client.get(url)
            codigo = respuesta.status_code
            tamano = len(respuesta.content)
        except Exception:
            codigo = 500
            tamano = 0
            
    return {
        "url": url,
        "status": codigo,
        "size": tamano,
        "time": time.time() - inicio
    }

def calcular_hash_pesado(texto: str, iteraciones: int):
    """Función puramente CPU-bound. Se ejecuta en otro proceso."""
    resultado = texto.encode()
    for _ in range(iteraciones):
        resultado = hashlib.sha256(resultado).digest()
    return resultado.hex()

async def worker(worker_id: int):
    loop = asyncio.get_running_loop()
    while True:
        try:
            tarea_data = await task_queue.get()
            tarea_id = tarea_data["id"]
            tipo_tarea = tarea_data["tipo"]
            
            tareas_db[tarea_id]["estado"] = "ejecutando"
            print(f"Worker {worker_id} ejecutando tarea {tarea_id} ({tipo_tarea})")
            
            if tipo_tarea == "esperar":
                await asyncio.sleep(5)
                
            elif tipo_tarea == "descargar":
                urls = tarea_data.get("urls", [])
                corrutinas = [descargar_url(url) for url in urls]
                tareas_db[tarea_id]["resultado"] = await asyncio.gather(*corrutinas)
                
            elif tipo_tarea == "hashear":
                texto = tarea_data.get("texto", "")
                iteraciones = tarea_data.get("iteraciones", 100000)
                # Delegamos el cálculo pesado para no bloquear el event loop
                resultado = await loop.run_in_executor(
                    process_pool, 
                    calcular_hash_pesado, 
                    texto, 
                    iteraciones
                )
                tareas_db[tarea_id]["resultado"] = resultado
                
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
    process_pool.shutdown(wait=True)

app = FastAPI(lifespan=lifespan)

@app.post("/tareas")
async def encolar_tarea(payload: TareaPayload):
    tarea_id = str(uuid.uuid4())
    tareas_db[tarea_id] = {"estado": "pendiente"}
    
    await task_queue.put({
        "id": tarea_id, 
        "tipo": payload.tipo,
        "urls": payload.urls,
        "texto": payload.texto,
        "iteraciones": payload.iteraciones
    })
    
    return {"id": tarea_id, "estado": "pendiente"}

@app.get("/tareas")
async def listar_tareas():
    return tareas_db

@app.get("/tareas/{id}")
async def obtener_tarea(id: str):
    return tareas_db.get(id, {"error": "Tarea no encontrada"})

@app.delete("/tareas/{id}")
async def cancelar_tarea(id: str):
    return {"mensaje": f"Tarea {id} cancelada (simulado)"}

@app.get("/estadisticas")
async def obtener_estadisticas():
    return {"pendientes": 0, "ejecutando": 0, "completadas": 0}

if __name__ == '__main__':
    uvicorn.run("src.main:app", host='0.0.0.0', port=8000, reload=True)