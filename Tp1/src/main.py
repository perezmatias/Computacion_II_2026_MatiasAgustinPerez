import multiprocessing
import time
from recolector import iniciar_recolector
from analizadores.memoria import iniciar_analizador_memoria
from analizadores.fds import iniciar_analizador_fds
from analizadores.sistema import iniciar_analizador_sistema
from analizadores.threads import iniciar_analizador_threads

def main():
    print("=== MONITOR DE PROCESOS Y THREADS ===")

    # 1. MEMORIA COMPARTIDA (Snapshot Global con Manager)
    manager = multiprocessing.Manager()
    snapshot_global = manager.dict()
    
    # Inicializamos las claves vacías en el diccionario compartido
    snapshot_global['memoria'] = {}
    snapshot_global['fds'] = {}
    snapshot_global['sistema'] = {}
    snapshot_global['threads'] = {}
    snapshot_global['senales'] = {}
    snapshot_global['scheduling'] = {}
    snapshot_global['resumen'] = {}

    # 2. COMUNICACIÓN IPC (Colas independientes por analizador)
    colas_analizadores = {
        'resumen': multiprocessing.Queue(),
        'memoria': multiprocessing.Queue(),
        'fds': multiprocessing.Queue(),
        'threads': multiprocessing.Queue(),
        'senales': multiprocessing.Queue(),
        'scheduling': multiprocessing.Queue(),
        'sistema': multiprocessing.Queue()
    }

    # 3. CREACIÓN Y CONFIGURACIÓN DE PROCESOS
    procesos = []

    # Proceso Recolector (Productor)
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

    # Analizador de Threads
    p_threads = multiprocessing.Process(
        target=iniciar_analizador_threads,
        args=(colas_analizadores['threads'], snapshot_global)
    )
    procesos.append(p_threads)

    # 4. ARRANQUE DE TODOS LOS PROCESOS EN PARALELO
    for p in procesos:
        p.start()

    try:
        # Loop principal de monitoreo en consola para verificar el estado del snapshot
        while True:
            time.sleep(2)
            mem_count = len(snapshot_global.get('memoria', {}))
            fds_count = len(snapshot_global.get('fds', {}))
            sis_count = len(snapshot_global.get('sistema', {}))
            thr_count = len(snapshot_global.get('threads', {}))
            
            print(f"[MAIN] Snapshot activo -> Memoria: {mem_count} | FDs: {fds_count} | Sistema: {sis_count} | Threads: {thr_count} (PIDs procesados)")
            
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