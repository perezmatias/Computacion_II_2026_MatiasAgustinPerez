import multiprocessing
import time
from recolector import iniciar_recolector
from analizadores.memoria import iniciar_analizador_memoria
from analizadores.fds import iniciar_analizador_fds
from analizadores.sistema import iniciar_analizador_sistema

def main():
    print("=== MONITOR DE PROCESOS Y THREADS ===")

    # 1. MEMORIA COMPARTIDA (Snapshot Global)
    manager = multiprocessing.Manager()
    snapshot_global = manager.dict()
    
    # Inicializamos las claves vacías
    snapshot_global['memoria'] = {}
    snapshot_global['fds'] = {}
    snapshot_global['sistema'] = {}

    # 2. COMUNICACIÓN IPC (Colas independientes)
    colas_analizadores = {
        'resumen': multiprocessing.Queue(),
        'memoria': multiprocessing.Queue(),
        'fds': multiprocessing.Queue(),
        'threads': multiprocessing.Queue(),
        'senales': multiprocessing.Queue(),
        'scheduling': multiprocessing.Queue(),
        'sistema': multiprocessing.Queue()
    }

    # 3. CREACIÓN Y ARRANQUE DE PROCESOS
    procesos = []

    # Proceso Recolector
    p_recolector = multiprocessing.Process(
        target=iniciar_recolector, 
        args=(colas_analizadores,)
    )
    procesos.append(p_recolector)

    # Analizador de Memoria
    p_memoria = multiprocessing.Process(
        target=iniciar_analizador_memoria,
        args=(colas_analizadores['memoria'], snapshot_global)
    )
    procesos.append(p_memoria)

    # Analizador de FDs
    p_fds = multiprocessing.Process(
        target=iniciar_analizador_fds,
        args=(colas_analizadores['fds'], snapshot_global)
    )
    procesos.append(p_fds)

    # Analizador de Sistema
    p_sistema = multiprocessing.Process(
        target=iniciar_analizador_sistema,
        args=(colas_analizadores['sistema'], snapshot_global)
    )
    procesos.append(p_sistema)

    # Iniciamos todos los procesos
    for p in procesos:
        p.start()

    try:
        # Loop principal que muestra el estado del snapshot global en tiempo real
        while True:
            time.sleep(2)
            mem_count = len(snapshot_global.get('memoria', {}))
            fds_count = len(snapshot_global.get('fds', {}))
            sis_count = len(snapshot_global.get('sistema', {}))
            
            print(f"[MAIN] Snapshot activo -> Memoria: {mem_count} PIDs | FDs: {fds_count} PIDs | Sistema: {sis_count} PIDs")
            
    except KeyboardInterrupt:
        print("\n[MAIN] Apagando monitor (SIGINT detectado)...")
    finally:
        # Shutdown limpio de todos los procesos hijos
        for p in procesos:
            p.terminate()
            p.join()
        print("[MAIN] Todos los procesos finalizados correctamente.")

if __name__ == "__main__":
    main()