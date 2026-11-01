"""Demo: encola más tareas que workers y muestra /estadisticas en vivo."""
import time

import requests

url = "http://localhost:8000"
for i in range(5):
    requests.post(f"{url}/tareas", json={"tipo": "esperar", "tiempo": 10})
    print(f"Tarea {i + 1} enviada")

time.sleep(0.5)
print("\nEstado del sistema:", requests.get(f"{url}/estadisticas").json())