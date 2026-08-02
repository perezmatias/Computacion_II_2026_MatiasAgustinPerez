import os
import time

def obtener_pids():
    pids = []
    try:
        for elemento in os.listdir('/proc'):
            if elemento.isdigit():
                pids.append(elemento)
    except FileNotFoundError:
        pass
    return pids

def iniciar_recolector(colas, intervalo=2.0):
    print("[RECOLECTOR] Proceso iniciado y repartiendo trabajo...")

    while True:
        pids = obtener_pids()

        for nombre_analizador, cola_especifica in colas.items():
            cola_especifica.put(pids)

        time.sleep(intervalo)