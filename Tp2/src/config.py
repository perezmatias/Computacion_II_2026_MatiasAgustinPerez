"""Configuración del servicio. Todo se puede cambiar con variables de entorno."""
import os


def _env(nombre: str, defecto, tipo=str):
    return tipo(os.getenv(nombre, defecto))


# Corrutinas worker que consumen la cola (= tareas que corren a la vez).
WORKERS = _env("WORKERS", 3, int)
# Procesos del ProcessPoolExecutor (solo para tareas CPU-bound).
POOL_PROCESSES = _env("POOL_PROCESSES", 2, int)
# Capacidad máxima de la cola. Si se llena, POST /tareas responde 503.
QUEUE_MAXSIZE = _env("QUEUE_MAXSIZE", 1000, int)
# Timeout por defecto de una tarea (segundos) si el cliente no manda uno.
DEFAULT_TIMEOUT = _env("DEFAULT_TIMEOUT", 30.0, float)
# Timeout de cada request HTTP dentro de `descargar` (segundos).
HTTP_TIMEOUT = _env("HTTP_TIMEOUT", 15.0, float)
# Cuánto esperar a las tareas en curso al apagar (segundos).
# Debe ser menor que stop_grace_period de docker-compose (Docker mata a los 10 s por defecto).
SHUTDOWN_GRACE = _env("SHUTDOWN_GRACE", 10.0, float)
# Carpeta donde se escriben/leen los volcados estado_<timestamp>.json.
DUMP_DIR = _env("DUMP_DIR", ".")
# "executor": hashear va a un ProcessPoolExecutor (correcto).
# "bloqueante": hashear corre dentro del event loop (SOLO para la medición 2).
HASH_MODE = _env("HASH_MODE", "executor")
