import requests
import time

url = "http://localhost:8000"

for i in range(5):
    requests.post(f"{url}/tareas", json={"tipo": "esperar", "tiempo": 10})
    print(f"Tarea {i+1} enviada")

time.sleep(0.5)
estadisticas = requests.get(f"{url}/estadisticas").json()
print("\nEstado del sistema:", estadisticas)