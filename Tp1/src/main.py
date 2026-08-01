import multiprocessing
import time
import curses
import signal
import json
from recolector import iniciar_recolector
from analizadores.memoria import iniciar_analizador_memoria
from analizadores.fds import iniciar_analizador_fds
from analizadores.sistema import iniciar_analizador_sistema
from analizadores.threads import iniciar_analizador_threads
from analizadores.senales import iniciar_analizador_senales
from analizadores.scheduling import iniciar_analizador_scheduling
from analizadores.resumen import iniciar_analizador_resumen
from tui import dibujar_interfaz

def main():
    # 1. MEMORIA COMPARTIDA
    manager = multiprocessing.Manager()
    snapshot_global = manager.dict()
    
    for clave in ['memoria', 'fds', 'sistema', 'threads', 'senales', 'scheduling', 'resumen']:
        snapshot_global[clave] = {}

    # 2. COMUNICACIÓN IPC
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
    procesos.append(multiprocessing.Process(target=iniciar_recolector, args=(colas_analizadores,)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_resumen, args=(colas_analizadores['resumen'], snapshot_global)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_memoria, args=(colas_analizadores['memoria'], snapshot_global)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_fds, args=(colas_analizadores['fds'], snapshot_global)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_sistema, args=(colas_analizadores['sistema'], snapshot_global)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_threads, args=(colas_analizadores['threads'], snapshot_global)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_senales, args=(colas_analizadores['senales'], snapshot_global)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_scheduling, args=(colas_analizadores['scheduling'], snapshot_global)))

    for p in procesos:
        p.start()

    # --- MANEJO DE SEÑALES ---
    def manejador_dump(signum, frame):
        """Atrapa SIGUSR1 y guarda el snapshot actual en un JSON."""
        # Convertimos el Manager.dict a un diccionario normal de Python
        estado_actual = {k: v for k, v in snapshot_global.items()}
        try:
            with open("dump_estado.json", "w") as archivo:
                json.dump(estado_actual, archivo, indent=4)
        except Exception:
            pass
            
    # Le decimos al S.O. que si llega la señal SIGUSR1, ejecute la función
    signal.signal(signal.SIGUSR1, manejador_dump)

    # 4. INTERFAZ GRÁFICA
    try:
        curses.wrapper(dibujar_interfaz, snapshot_global)
    except KeyboardInterrupt:
        pass # Apagado limpio con Ctrl+C (SIGINT)
    finally:
        for p in procesos:
            p.terminate()
            p.join()
        print("Monitor apagado correctamente.")

if __name__ == "__main__":
    main()