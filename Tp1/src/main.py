import multiprocessing
import time
from recolector import iniciar_recolector
# Importamos la función de nuestro nuevo analizador
from analizadores.memoria import iniciar_analizador_memoria

def main():
    print("Iniciando Monitor de Procesos...")

    # --- MEMORIA COMPARTIDA ---
    # Creamos el Manager. Esto levanta un proceso "servidor" invisible
    manager = multiprocessing.Manager()
    
    # Este es nuestro "pizarrón global" seguro para multiprocesos
    snapshot_global = manager.dict()
    
    # Inicializamos la clave de memoria vacía para que la interfaz gráfica
    # no tire error si intenta leer antes de que el analizador escriba algo.
    snapshot_global['memoria'] = {}

    # --- COMUNICACIÓN (COLAS) ---
    colas_analizadores = {
        'resumen': multiprocessing.Queue(),
        'memoria': multiprocessing.Queue(),
        'fds': multiprocessing.Queue(),
        'threads': multiprocessing.Queue(),
        'senales': multiprocessing.Queue(),
        'scheduling': multiprocessing.Queue(),
        'sistema': multiprocessing.Queue()
    }

    # --- LEVANTAMOS LOS PROCESOS ---
    # 1. El Recolector (le pasamos todas las colas)
    proceso_recolector = multiprocessing.Process(
        target=iniciar_recolector, 
        args=(colas_analizadores,)
    )
    proceso_recolector.start()

    # 2. El Analizador de Memoria (le pasamos SU cola y el pizarrón global)
    proceso_memoria = multiprocessing.Process(
        target=iniciar_analizador_memoria,
        args=(colas_analizadores['memoria'], snapshot_global)
    )
    proceso_memoria.start()

    try:
        # Loop temporal para verificar que el snapshot se está llenando
        while True:
            # Leemos directamente del snapshot global
            diccionario_memoria = snapshot_global['memoria']
            print(f"[MAIN] Snapshot global actualizado: {len(diccionario_memoria)} procesos en memoria.")
            time.sleep(3)
            
    except KeyboardInterrupt:
        print("\nApagando monitor...")
    finally:
        # Limpieza de procesos al salir con Ctrl+C
        proceso_recolector.terminate()
        proceso_memoria.terminate()
        proceso_recolector.join()
        proceso_memoria.join()
        print("Monitor apagado correctamente.")

if __name__ == "__main__":
    main()