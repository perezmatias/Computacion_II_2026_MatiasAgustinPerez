import multiprocessing
import time
from recolector import iniciar_recolector
from analizadores.memoria import iniciar_analizador_memoria
from analizadores.fds import iniciar_analizador_fds
from analizadores.sistema import iniciar_analizador_sistema
from analizadores.threads import iniciar_analizador_threads
from analizadores.senales import iniciar_analizador_senales
from analizadores.scheduling import iniciar_analizador_scheduling
from analizadores.resumen import iniciar_analizador_resumen # <-- IMPORTAMOS RESUMEN

def main():
    print("=== MONITOR DE PROCESOS Y THREADS (MOTOR INICIADO) ===")

    # 1. MEMORIA COMPARTIDA (El pizarrón central)
    manager = multiprocessing.Manager()
    snapshot_global = manager.dict()
    
    snapshot_global['memoria'] = {}
    snapshot_global['fds'] = {}
    snapshot_global['sistema'] = {}
    snapshot_global['threads'] = {}
    snapshot_global['senales'] = {}
    snapshot_global['scheduling'] = {}
    snapshot_global['resumen'] = {} # <-- INICIALIZAMOS RESUMEN

    # 2. COMUNICACIÓN IPC (Las 7 bandejas de entrada)
    colas_analizadores = {
        'resumen': multiprocessing.Queue(),
        'memoria': multiprocessing.Queue(),
        'fds': multiprocessing.Queue(),
        'threads': multiprocessing.Queue(),
        'senales': multiprocessing.Queue(),
        'scheduling': multiprocessing.Queue(),
        'sistema': multiprocessing.Queue()
    }

    # 3. CREACIÓN DE LA ORQUESTA (Procesos)
    procesos = []

    p_recolector = multiprocessing.Process(target=iniciar_recolector, args=(colas_analizadores,))
    procesos.append(p_recolector)

    p_resumen = multiprocessing.Process(target=iniciar_analizador_resumen, args=(colas_analizadores['resumen'], snapshot_global))
    procesos.append(p_resumen)

    p_memoria = multiprocessing.Process(target=iniciar_analizador_memoria, args=(colas_analizadores['memoria'], snapshot_global))
    procesos.append(p_memoria)

    p_fds = multiprocessing.Process(target=iniciar_analizador_fds, args=(colas_analizadores['fds'], snapshot_global))
    procesos.append(p_fds)

    p_sistema = multiprocessing.Process(target=iniciar_analizador_sistema, args=(colas_analizadores['sistema'], snapshot_global))
    procesos.append(p_sistema)

    p_threads = multiprocessing.Process(target=iniciar_analizador_threads, args=(colas_analizadores['threads'], snapshot_global))
    procesos.append(p_threads)

    p_senales = multiprocessing.Process(target=iniciar_analizador_senales, args=(colas_analizadores['senales'], snapshot_global))
    procesos.append(p_senales)

    p_scheduling = multiprocessing.Process(target=iniciar_analizador_scheduling, args=(colas_analizadores['scheduling'], snapshot_global))
    procesos.append(p_scheduling)

    # 4. ARRANQUE EN PARALELO
    for p in procesos:
        p.start()

    try:
        # Loop principal (Por ahora imprime en consola, luego será la TUI)
        while True:
            time.sleep(2)
            res_count = len(snapshot_global.get('resumen', {}))
            
            print(f"[MAIN] ¡Motor corriendo! {res_count} procesos monitoreados simultáneamente en 7 módulos.")
            
    except KeyboardInterrupt:
        print("\n[MAIN] Apagando monitor (SIGINT detectado)...")
    finally:
        for p in procesos:
            p.terminate()
            p.join()
        print("[MAIN] Todos los procesos finalizados correctamente.")

if __name__ == "__main__":
    main()