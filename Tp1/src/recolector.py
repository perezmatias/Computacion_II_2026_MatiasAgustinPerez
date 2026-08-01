import os
import time

def obtener_pids():
    """
    Lee directamente /proc y devuelve una lista con los PIDs válidos.
    """
    pids = []
    try:
        # Listamos el directorio /proc
        for elemento in os.listdir('/proc'):
            # Filtramos para quedarnos solo con carpetas numéricas
            if elemento.isdigit():
                pids.append(elemento)
    except FileNotFoundError:
        pass
    
    return pids

def iniciar_recolector(cola_pids, intervalo=2.0):
    """
    Función objetivo del proceso Recolector.
    Se ejecuta en un loop infinito enviando datos por la cola.
    """
    print("[RECOLECTOR] Proceso iniciado y leyendo /proc...")
    
    while True:
        # Obtenemos la lista de PIDs vivos en este instante
        pids = obtener_pids()
        
        # Metemos la lista completa en la cola de comunicación
        cola_pids.put(pids)
        
        # Pausa antes del próximo escaneo (esto luego se configurará dinámicamente)
        time.sleep(intervalo)