import asyncio
import uuid
import time
import hashlib
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import uvicorn

task_queue = asyncio.Queue()
WORKERS_COUNT = 3
tareas_db = {}
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
            
            # Guardamos el estado y la referencia a ESTA corrutina
            tareas_db[tarea_id]["estado"] = "ejecutando"
            tareas_db[tarea_id]["task"] = asyncio.current_task()
            
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
                resultado = await loop.run_in_executor(
                    process_pool, 
                    calcular_hash_pesado, 
                    texto, 
                    iteraciones
                )
                tareas_db[tarea_id]["resultado"] = resultado
                
            tareas_db[tarea_id]["estado"] = "completada"
            # Limpiamos la referencia para no gastar memoria
            tareas_db[tarea_id].pop("task", None)
            
            task_queue.task_done()
            
        except asyncio.CancelledError:
            # Si nos cancelan, capturamos la excepción y actualizamos el estado
            print(f"Worker {worker_id}: Tarea {tarea_id} CANCELADA")
            tareas_db[tarea_id]["estado"] = "cancelada"
            tareas_db[tarea_id].pop("task", None)
            task_queue.task_done()
            # No hacemos break porque queremos que el worker siga vivo para otras tareas

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
    # Devolvemos todo menos los objetos Task, que no son serializables a JSON
    return {
        tid: {k: v for k, v in info.items() if k != "task"}
        for tid, info in tareas_db.items()
    }

@app.get("/tareas/{id}")
async def obtener_tarea(id: str):
    if id not in tareas_db:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    tarea_info = tareas_db[id].copy()
    tarea_info.pop("task", None)
    return tarea_info

@app.delete("/tareas/{id}")
async def cancelar_tarea(id: str):
    if id not in tareas_db:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
    estado_actual = tareas_db[id]["estado"]
    
    if estado_actual == "completada" or estado_actual == "cancelada":
        return {"mensaje": f"La tarea ya estaba {estado_actual}"}
        
    if estado_actual == "ejecutando":
        # Extraemos el objeto Task y le pedimos que se cancele
        task_obj = tareas_db[id].get("task")
        if task_obj:
            task_obj.cancel()
            return {"mensaje": "Cancelación solicitada al worker"}
            
    # Si estaba "pendiente" (en la cola, aún no la tomó ningún worker)
    if estado_actual == "pendiente":
        tareas_db[id]["estado"] = "cancelada"
        return {"mensaje": "Tarea cancelada antes de ejecutarse"}

@app.get("/estadisticas")
async def obtener_estadisticas():
    return {"pendientes": 0, "ejecutando": 0, "completadas": 0}

if __name__ == '__main__':
    uvicorn.run("src.main:app", host='0.0.0.0', port=8000, reload=True)