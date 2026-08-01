import os
import time

def obtener_pids():
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

def iniciar_recolector(colas, intervalo=2.0):
    print("[RECOLECTOR] Proceso iniciado y repartiendo trabajo...")
    
    while True:
        pids = obtener_pids()
        
        # Multiplexación: enviamos copia a cada cola
        for nombre_analizador, cola_especifica in colas.items():
            cola_especifica.put(pids)
        
        time.sleep(intervalo)