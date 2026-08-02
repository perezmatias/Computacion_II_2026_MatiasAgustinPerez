import multiprocessing
import time
import curses
import signal
import json
import os
from recolector import iniciar_recolector
from analizadores.memoria import iniciar_analizador_memoria
from analizadores.fds import iniciar_analizador_fds
from analizadores.sistema import iniciar_analizador_sistema
from analizadores.sistema_global import iniciar_analizador_sistema_global
from analizadores.threads import iniciar_analizador_threads
from analizadores.senales import iniciar_analizador_senales
from analizadores.scheduling import iniciar_analizador_scheduling
from analizadores.resumen import iniciar_analizador_resumen
from tui import dibujar_interfaz

CONFIG_PATH = "config.json"

# (default, minimo, maximo) por vista, según la tabla de la consigna
LIMITES_INTERVALO = {
    '1': {"clave": "resumen",        "default": 2.0,  "minimo": 0.5, "maximo": 30.0},
    '2': {"clave": "memoria",        "default": 3.0,  "minimo": 1.0, "maximo": 30.0},
    '3': {"clave": "fds",            "default": 5.0,  "minimo": 2.0, "maximo": 30.0},
    '4': {"clave": "sistema",        "default": 2.0,  "minimo": 0.5, "maximo": 30.0},
    '5': {"clave": "threads",        "default": 2.0,  "minimo": 0.5, "maximo": 30.0},
    '6': {"clave": "senales",        "default": 10.0, "minimo": 5.0, "maximo": 60.0},
    '7': {"clave": "scheduling",     "default": 10.0, "minimo": 5.0, "maximo": 60.0},
    '8': {"clave": "sistema_global", "default": 2.0,  "minimo": 1.0, "maximo": 30.0},
}


def cargar_config():
    defaults = {f"intervalo_{v['clave']}": v["default"] for v in LIMITES_INTERVALO.values()}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                return {**defaults, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


def main():
    manager = multiprocessing.Manager()
    snapshot_global = manager.dict()

    for clave in ['memoria', 'fds', 'sistema', 'sistema_global', 'threads',
                  'senales', 'scheduling', 'resumen']:
        snapshot_global[clave] = {}

    config = cargar_config()

    # Un multiprocessing.Value por analizador: memoria compartida real,
    # así el analizador lo lee y la TUI lo escribe con +/- sin pasar por el Manager.
    intervalos = {}
    for info in LIMITES_INTERVALO.values():
        clave = info["clave"]
        valor_inicial = config.get(f"intervalo_{clave}", info["default"])
        intervalos[clave] = multiprocessing.Value('d', valor_inicial)

    colas_analizadores = {
        'resumen': multiprocessing.Queue(),
        'memoria': multiprocessing.Queue(),
        'fds': multiprocessing.Queue(),
        'threads': multiprocessing.Queue(),
        'senales': multiprocessing.Queue(),
        'scheduling': multiprocessing.Queue(),
        'sistema': multiprocessing.Queue(),
    }

    procesos = []
    procesos.append(multiprocessing.Process(target=iniciar_recolector, args=(colas_analizadores,)))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_resumen, args=(colas_analizadores['resumen'], snapshot_global, intervalos['resumen'])))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_memoria, args=(colas_analizadores['memoria'], snapshot_global, intervalos['memoria'])))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_fds, args=(colas_analizadores['fds'], snapshot_global, intervalos['fds'])))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_sistema, args=(colas_analizadores['sistema'], snapshot_global, intervalos['sistema'])))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_threads, args=(colas_analizadores['threads'], snapshot_global, intervalos['threads'])))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_senales, args=(colas_analizadores['senales'], snapshot_global, intervalos['senales'])))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_scheduling, args=(colas_analizadores['scheduling'], snapshot_global, intervalos['scheduling'])))
    procesos.append(multiprocessing.Process(target=iniciar_analizador_sistema_global, args=(snapshot_global, intervalos['sistema_global'])))

    for p in procesos:
        p.start()

    # --- MANEJO DE SEÑALES DEL MONITOR ---

    def manejador_dump(signum, frame):
        """SIGUSR1: guarda el snapshot actual en un JSON."""
        estado_actual = {k: v for k, v in snapshot_global.items()}
        try:
            with open("dump_estado.json", "w") as archivo:
                json.dump(estado_actual, archivo, indent=4, default=str)
        except Exception:
            pass

    def manejador_reload(signum, frame):
        """SIGHUP: recarga config.json y actualiza los Value en caliente."""
        nueva_config = cargar_config()
        for info in LIMITES_INTERVALO.values():
            clave = info["clave"]
            nuevo_valor = nueva_config.get(f"intervalo_{clave}", info["default"])
            with intervalos[clave].get_lock():
                intervalos[clave].value = nuevo_valor

    def manejador_shutdown(signum, frame):
        """SIGTERM: mismo comportamiento que Ctrl+C (SIGINT)."""
        raise KeyboardInterrupt()

    signal.signal(signal.SIGUSR1, manejador_dump)
    signal.signal(signal.SIGHUP, manejador_reload)
    signal.signal(signal.SIGTERM, manejador_shutdown)

    try:
        curses.wrapper(dibujar_interfaz, snapshot_global, intervalos, LIMITES_INTERVALO)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procesos:
            p.terminate()
            p.join()
        print("Monitor apagado correctamente.")


if __name__ == "__main__":
    main()