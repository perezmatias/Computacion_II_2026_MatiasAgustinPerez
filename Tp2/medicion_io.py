import requests
import time

url_api = "http://localhost:8000/tareas"
url_prueba = "https://httpbin.org/delay/2"
urls_20 = [url_prueba for _ in range(20)]

def esperar_tarea(tarea_id):
    while True:
        res = requests.get(f"{url_api}/{tarea_id}").json()
        if res.get("estado") in ["completada", "fallida"]:
            return
        time.sleep(0.5)

print("--- Midiendo ejecución CONCURRENTE (20 URLs en 1 tarea) ---")
inicio_c = time.time()
res_c = requests.post(url_api, json={"tipo": "descargar", "urls": urls_20}).json()
esperar_tarea(res_c["id"])
tiempo_concurrente = time.time() - inicio_c
print(f"Tiempo concurrente total: {tiempo_concurrente:.2f} segundos\n")

print("--- Midiendo ejecución SECUENCIAL (20 tareas de 1 URL separadas) ---")
inicio_s = time.time()
for i in range(20):
    res_s = requests.post(url_api, json={"tipo": "descargar", "urls": [url_prueba]}).json()
    esperar_tarea(res_s["id"])
tiempo_secuencial = time.time() - inicio_s
print(f"Tiempo secuencial total: {tiempo_secuencial:.2f} segundos\n")

speedup = tiempo_secuencial / tiempo_concurrente
print(f"--- RESULTADOS FINALES ---")
print(f"Speedup calculado: {speedup:.2f}x")