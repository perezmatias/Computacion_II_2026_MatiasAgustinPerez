import multiprocessing
import time
from recolector import iniciar_recolector

def main():
    print("Iniciando Monitor de Procesos...")

    # 1. Creamos la Cola de comunicación (IPC)
    cola_pids = multiprocessing.Queue()

    # 2. Definimos el proceso Recolector
    # Le pasamos la cola para que sepa dónde guardar los PIDs que encuentre
    proceso_recolector = multiprocessing.Process(
        target=iniciar_recolector, 
        args=(cola_pids,)
    )

    # 3. Iniciamos el proceso
    proceso_recolector.start()

    # (Acá a futuro irán los procesos de los analizadores y el agregador)

    try:
        # Un loop infinito temporal solo para mantener vivo el proceso principal
        # y ver cómo la cola se va llenando.
        while True:
            # Leemos de la cola (si hay algo) sin bloquear el proceso
            if not cola_pids.empty():
                pids_actuales = cola_pids.get()
                print(f"[MAIN] PIDs recibidos desde la cola: {len(pids_actuales)} procesos encontrados.")
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nApagando monitor (SIGINT detectado)...")
    finally:
        # Limpieza de procesos (Shutdown limpio)
        proceso_recolector.terminate()
        proceso_recolector.join()
        print("Monitor apagado correctamente.")

if __name__ == "__main__":
    main()