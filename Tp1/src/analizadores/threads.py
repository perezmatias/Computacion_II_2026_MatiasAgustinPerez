import os
import time

def iniciar_analizador_threads(cola_in, snapshot_global, intervalo=2.0):
    """
    Proceso que lee PIDs, cuenta los hilos (LWPs) en /proc/<pid>/task/
    y actualiza el snapshot global.
    """
    print("[THREADS] Analizador listo y esperando PIDs...")
    
    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_threads = {}
            
            for pid in pids:
                ruta_task = f"/proc/{pid}/task"
                
                try:
                    # Listamos la carpeta task y contamos la cantidad de elementos
                    cantidad_threads = len(os.listdir(ruta_task))
                    datos_threads[pid] = {"cantidad_hilos": cantidad_threads}
                    
                except FileNotFoundError:
                    pass
                except PermissionError:
                    pass
                
            snapshot_global['threads'] = datos_threads
            
        time.sleep(intervalo)