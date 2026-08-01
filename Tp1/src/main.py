import multiprocessing
import time
from recolector import iniciar_recolector

def main():
    print("Iniciando Monitor de Procesos...")

    # Creamos un diccionario con una cola independiente para cada analizador
    colas_analizadores = {
        'resumen': multiprocessing.Queue(),
        'memoria': multiprocessing.Queue(),
        'fds': multiprocessing.Queue(),
        'threads': multiprocessing.Queue(),
        'senales': multiprocessing.Queue(),
        'scheduling': multiprocessing.Queue(),
        'sistema': multiprocessing.Queue()
    }

    # Definimos el proceso Recolector y le pasamos todas las colas
    proceso_recolector = multiprocessing.Process(
        target=iniciar_recolector, 
        args=(colas_analizadores,)
    )

    # Iniciamos el recolector
    proceso_recolector.start()

    try:
        # Loop temporal para probar
        while True:
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nApagando monitor...")
    finally:
        proceso_recolector.terminate()
        proceso_recolector.join()
        print("Monitor apagado correctamente.")

if __name__ == "__main__":
    main()