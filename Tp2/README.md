# TP2 — Plataforma de Tareas Distribuidas

**Computación II — Universidad de Mendoza — 2026** · Matías Agustín Pérez

Servicio HTTP que recibe trabajos, los ejecuta de forma concurrente y permite
consultar su estado y resultado. Construido con FastAPI y `asyncio`, sin frameworks
de colas: la cola y el pool de workers están implementados a mano.

> Este proyecto está en la carpeta `Tp2/` del repositorio. Todos los comandos de este
> documento se corren desde ahí.

---

## 1. Descripción y uso

### Qué hace

El cliente encola tareas con `POST /tareas` y recibe un `id` al instante. Un pool de
workers (corrutinas) las consume de una `asyncio.Queue`. Hay tres tipos de tarea:

| Tipo | Naturaleza | Cómo se ejecuta |
|------|-----------|-----------------|
| `descargar` | I/O-bound | `httpx.AsyncClient` y `asyncio.gather`: todas las URLs a la vez |
| `hashear` | CPU-bound | `run_in_executor` sobre un `ProcessPoolExecutor`, en tandas |
| `esperar` | I/O simulado | `asyncio.sleep` |

Estados posibles: `pendiente`, `ejecutando`, `completada`, `fallida`, `cancelada`.

### Cómo levantarlo

```bash
docker compose up --build
```

Levanta dos servicios: `api` (el sistema) y `mock` (un servidor local con demora
configurable, usado para las mediciones sin depender de internet).

### Ejemplos de uso

```bash
# Encolar tareas (responden 202 al instante)
curl -X POST localhost:8000/tareas -H 'content-type: application/json' \
     -d '{"tipo":"esperar","tiempo":10,"timeout":30}'

curl -X POST localhost:8000/tareas -H 'content-type: application/json' \
     -d '{"tipo":"descargar","urls":["https://example.com","http://mock:9000/delay/2"]}'

curl -X POST localhost:8000/tareas -H 'content-type: application/json' \
     -d '{"tipo":"hashear","texto":"hola","iteraciones":5000000}'

# Consultar
curl localhost:8000/tareas                        # listar todas
curl 'localhost:8000/tareas?estado=ejecutando'    # filtrar por estado
curl localhost:8000/tareas/<id>                   # estado y resultado
curl localhost:8000/estadisticas                  # totales, tiempos promedio, workers ocupados

# Cancelar (tarea encolada o en ejecución)
curl -X DELETE localhost:8000/tareas/<id>
```

La URL `http://mock:9000/...` solo se resuelve dentro de la red de Docker Compose,
porque la descarga la hace el contenedor de la API.

### Configuración (variables de entorno)

| Variable | Defecto | Qué controla |
|----------|---------|--------------|
| `WORKERS` | 3 | Corrutinas worker (tareas simultáneas) |
| `POOL_PROCESSES` | 2 | Procesos del `ProcessPoolExecutor` (solo `hashear`) |
| `QUEUE_MAXSIZE` | 1000 | Capacidad de la cola; si se llena, `POST` responde 503 |
| `DEFAULT_TIMEOUT` | 30 | Timeout por tarea (s) si el cliente no manda uno |
| `SHUTDOWN_GRACE` | 10 | Cuánto esperar a las tareas en curso al apagar (s) |
| `HASH_MODE` | `executor` | `bloqueante` corre `hashear` en el event loop (**solo para la medición 2**) |

Ejemplo: `WORKERS=50 docker compose up --build`.

### Cómo se prueba

Con la API levantada, `bash verificar.sh` corre 21 comprobaciones automáticas
(validación, cancelación, errores, timeout, event loop libre, filtros y estadísticas) y
muestra `OK` o `FALLA` en cada una. Los volcados de estado quedan en `./data/`.

---

## 2. Arquitectura

```
 Cliente ──HTTP──> FastAPI (event loop, un solo hilo)
                     │ POST: encolar() → put_nowait(id)      GET / DELETE: leen o cancelan
                     ▼
              asyncio.Queue (maxsize)           motor.tareas  { id → registro }
                     │ get()                           ▲ estado / resultado
        ┌────────────┼────────────┐                    │
     worker 0     worker 1     worker N-1 ─────────────┘        (corrutinas)
        │  cada worker lanza UNA asyncio.Task por trabajo (cancelable por separado)
        ├─ esperar   → asyncio.sleep
        ├─ descargar → AsyncClient + gather
        └─ hashear   → run_in_executor ──> ProcessPoolExecutor (procesos hijos)
```

**Flujo de una tarea.** `POST` valida el payload, crea el registro en estado
`pendiente` y mete el `id` en la cola con `put_nowait`. Un worker lo saca, pasa la tarea a
`ejecutando` y lanza el trabajo en su propia `asyncio.Task`, envuelta en
`wait_for(timeout)`. Termina en `completada`, `fallida` (error o timeout) o `cancelada`.

**Estructura del código**

| Archivo | Responsabilidad |
|---------|-----------------|
| `src/main.py` | API: rutas, validación (Pydantic) y ciclo de vida (`lifespan`) |
| `src/motor.py` | Clase `Motor`: cola, workers, cancelación, timeouts, estadísticas y volcado |
| `src/config.py` | Parámetros leídos de variables de entorno |
| `src/mock_server.py` | Servidor local con demora, para las mediciones |
| `mediciones/` | Scripts de las tres mediciones y una demo de saturación |
| `verificar.sh` | Batería de comprobaciones automáticas |

---

## 3. Decisiones de diseño

### ¿Por qué `asyncio.Queue` y no `queue.Queue`?

`queue.Queue.get()` bloquea el **hilo** completo (espera con locks del sistema operativo).
Dentro de una corrutina, eso congelaría el event loop entero: ningún otro worker ni
endpoint avanzaría. `asyncio.Queue.get()` es un `await`: suspende solamente a esa
corrutina y le devuelve el control al loop, que sigue atendiendo a las demás.

Además, `asyncio.Queue` no necesita locks internos para un solo hilo, porque el loop
solo cambia de corrutina en los `await`. La cola es **acotada** (`QUEUE_MAXSIZE`) y se
usa `put_nowait`: si está llena, `POST` responde 503 en vez de aceptar trabajo sin
límite hasta agotar la memoria.

### ¿Cómo evito que una tarea CPU-bound congele la API?

Un event loop corre en un solo hilo. Si una corrutina calcula durante 2 segundos sin
ningún `await`, nada más avanza en ese lapso. Por eso `hashear` se delega con
`loop.run_in_executor` a un `ProcessPoolExecutor`: el cálculo corre en otro proceso, con
su propio intérprete, su propio GIL y otro núcleo, y el loop solo hace `await` del
resultado.

Elegí **procesos y no threads** por el GIL: dos threads no ejecutan bytecode de Python
en paralelo, así que un hash en un thread seguiría compitiendo con el loop por el
intérprete. Los procesos evitan esa competencia. La medición 2 muestra la diferencia
con números (sección 4.2).

El hash se calcula en **tandas de 100.000 iteraciones**, enviando cada tanda al
executor por separado. Esto no cambia el resultado, pero permite que una cancelación o
un timeout se noten entre tandas (ver el punto siguiente).

### ¿Cómo implementé la cancelación y qué pasa con los recursos a medio usar?

Cada trabajo corre en su **propia `asyncio.Task`**, distinta de la del worker que lo
espera. `DELETE` llama a `job.cancel()` sobre esa tarea, lo que lanza `CancelledError`
en el `await` donde esté parada. El worker atrapa la cancelación, marca la tarea como
`cancelada` y **sigue vivo** para atender la próxima.

Qué pasa con los recursos, según el tipo:
- **`descargar`:** `asyncio.gather` cancela todas las descargas hijas y el
  `async with httpx.AsyncClient` cierra las conexiones al salir, incluso en cancelación.
- **`esperar`:** el `asyncio.sleep` se interrumpe al instante.
- **`hashear`:** un `ProcessPoolExecutor` no puede interrumpir una función ya iniciada. Por
  eso las tandas: tras cancelar no se envían más tandas, y a lo sumo termina la que está
  en curso (decenas de milisegundos). Sin tandas, el proceso hijo seguiría calculando
  "para nadie" y ocuparía uno de los procesos del pool.
- **Tarea `pendiente`:** se marca `cancelada` y sigue físicamente en la cola; el worker la
  descarta al sacarla.

Hay un detalle sutil: cuando el worker recibe un `CancelledError`, tiene que saber si
cancelaron **al trabajo** (`DELETE`) o **al propio worker** (apagado). Lo distingue con
`asyncio.current_task().cancelling()`: si es mayor que cero, cancelaron al worker y
re-lanza la excepción; si no, solo termina esa tarea y continúa.

### ¿Qué pasa si un worker lanza una excepción no capturada?

Hay dos redes de seguridad. `_ejecutar` captura cualquier `Exception` del trabajo y pasa
la tarea a `fallida` con el motivo en el campo `error`. Y el loop del worker captura
cualquier error inesperado, lo registra en el log y **sigue**. Así un fallo no mata al
worker ni deja la tarea en `ejecutando` para siempre.

En `descargar`, el error de cada URL se reporta **dentro del resultado** (`status: null` y
el mensaje en `error`) y la tarea queda `completada`: una URL rota no invalida las demás.

### Apagado ordenado

uvicorn captura `SIGTERM` y `SIGINT` y dispara el cierre del `lifespan`. Ahí:

1. Se deja de aceptar tareas nuevas (`aceptando = False`).
2. Se espera hasta `SHUTDOWN_GRACE` segundos a que terminen las tareas en curso.
3. Las que sigan se cancelan, con el motivo "Cancelada por apagado del servidor".
4. Se cancelan los workers y se cierra el pool con `asyncio.to_thread`, para no bloquear
   el loop.
5. Se vuelca el estado a `estado_<timestamp>.json`.

Las tareas que seguían `pendiente` quedan así en el volcado. `stop_grace_period` en
`docker-compose.yml` (20 s) es mayor que `SHUTDOWN_GRACE` (10 s); si fuera menor, Docker
mandaría `SIGKILL` antes de terminar el volcado. Lo comprobé: `docker compose stop` tardó
10,4 s y el contenedor salió con código 0.

Al arrancar, si existe un volcado previo, el motor lo reporta por log con el conteo de
tareas por estado.

### `httpx` vs `aiohttp`

Usé `httpx` en modo asíncrono (`httpx.AsyncClient`). La consigna prohíbe `requests`, y con
razón: es una librería **síncrona**, así que cada `requests.get()` bloquea el hilo mientras
espera la red, y como el event loop corre en ese mismo hilo, se congelarían todas las
corrutinas, incluidos los endpoints de la API. Hacen falta una librería cuyas llamadas
sean `await`, para que mientras una descarga espera, el loop pueda atender otras.

Entre las opciones asíncronas elegí `httpx` por tres razones. Primero, su API es casi
idéntica a la de `requests` (`client.get(url)`, `response.status_code`,
`response.content`), que ya conocía, lo que reduce errores. Segundo, permite configurar los
timeouts y las redirecciones de forma explícita al crear el cliente
(`AsyncClient(timeout=..., follow_redirects=True)`), y en este sistema los timeouts son
parte central del diseño. Tercero, se usa como context manager (`async with`), de modo
que el cliente y sus conexiones se cierran solos aunque la tarea se cancele a mitad de
una descarga, lo cual es exactamente el requisito de "cancelación limpia".

Creo un solo cliente por tarea y lanzo todas las descargas con `asyncio.gather`, así se
reutilizan las conexiones dentro de la tarea. `aiohttp` es una alternativa muy
madura y suele destacarse en escenarios de concurrencia muy alta; No medí `aiohttp`, así que no puedo comparar rendimientos. Para este sistema, la
concurrencia máxima la define el tamaño del pool de workers y no la librería HTTP, y
preferí la API más sencilla.

### Preguntas de la corrección

**¿Dónde podría bloquearse el event loop?** Los puntos honestos son: el modo
`HASH_MODE=bloqueante`, que existe solo para medir; `_volcar()`, que escribe un archivo
con E/S síncrona (ocurre al apagar, cuando ya no se atiende a nadie); y
`/estadisticas`, que recorre todas las tareas guardadas, un costo que crece con la
cantidad (ver 4.3). Cada tanda de `hash_tanda` corre en otro proceso, no en el loop.

**¿Por qué el pool no necesita un `Lock`?** Porque todo el código del motor corre en un
solo hilo y el loop solo puede cambiar de corrutina en un `await`. Una secuencia como
"leer el estado, modificar el diccionario" sin ningún `await` en el medio es atómica. Un
`Lock` haría falta con threads, o si entre dos `await` hubiera una operación compuesta
que otra corrutina pudiera ver a medias. Los procesos del executor no comparten memoria
con el loop, así que tampoco hay estado compartido que proteger.

**¿Diferencia entre `asyncio.gather` y un `for` con `await`?** Con un `for` y `await`
adentro, cada operación espera a que termine la anterior: el tiempo total es la suma. Con
`gather` se lanzan todas a la vez y se espera a todas: el tiempo total es el de la más
lenta. La medición 4.1 lo muestra con números.

**¿Por qué `time.sleep()` es un bug en una corrutina y `asyncio.sleep()` no?**
`time.sleep` bloquea el hilo, y como el event loop corre en ese hilo, se congelan todas
las corrutinas. `asyncio.sleep` es un `await`: suspende solo a la corrutina actual y
deja al loop atender a las otras.

**¿Qué pasa si cancelo una tarea a mitad de una descarga?** `CancelledError` se lanza en
el `await client.get(...)`; `gather` cancela las demás descargas de la tarea; el
`async with` cierra el cliente HTTP; el worker marca la tarea como `cancelada` y
continúa. `verificar.sh` comprueba que los workers siguen vivos tras cancelaciones
repetidas.

**¿Qué se rompe primero con 10.000 tareas de golpe?** Con la configuración por defecto,
la cola (límite de 1000): `POST` empieza a responder 503. Está medido (ver 4.3). Con la
cola ampliada a 20.000, no se rompió nada en las pruebas: la única señal fue que la
latencia de `/estadisticas` subió de forma suave (hipótesis en 4.3), y la memoria quedó
en ≈ 60 MiB con 10.000 tareas.

---

## 4. Mediciones

**Entorno:** Intel Core i7-1065G7 (4 núcleos, 8 hilos, 1,30 GHz base), Linux Mint, Docker Compose (Docker ve ≈ 11,25 GiB de RAM). Cliente y servidor corren en la
misma máquina, así que los tiempos de red son los del loopback. Los scripts están en
`mediciones/`.

### 4.1 Concurrencia I/O

`python3 mediciones/medicion_io.py` hace 20 descargas a un servidor local que demora 2 s.

| Modo | Tiempo |
|------|--------|
| 20 secuenciales (una tarea por vez) | **40,37 s** |
| 20 concurrentes (una tarea, `asyncio.gather`) | **2,05 s** |
| **Speedup** | **19,7×** |
| 20 tareas separadas con 3 workers | 14,18 s (speedup 2,8×) |

**Interpretación.** El secuencial da lo esperado: 20 × 2 s = 40 s (los 0,37 s extra son
el costo de crear y consultar cada tarea). El concurrente tarda lo que la más lenta
(2 s), no la suma: mientras una descarga espera la respuesta de la red, el event loop
atiende a las otras. Por eso alcanza **un solo hilo**: el sistema operativo avisa (con
`epoll`, clase 17) cuándo hay datos listos en cada socket y el loop no gasta un hilo
por conexión. El speedup (19,7×) está muy cerca del máximo teórico (20×) porque las
descargas son independientes y casi no hay trabajo de CPU.

La tercera fila muestra un límite de diseño: con 20 tareas **separadas**, solo
corren a la vez tantas como `WORKERS` (3): ⌈20/3⌉ rondas × 2 s ≈ 14 s. La concurrencia
**dentro** de una tarea (el `gather` sobre sus URLs) no tiene tope, pero **entre**
tareas lo pone el tamaño del pool.

*Nota:* se mide contra un servidor local con demora fija, no contra internet, así que
mide la concurrencia y no la variabilidad de una red real.

### 4.2 Event loop bloqueado

Una tarea `hashear` de 5.000.000 de iteraciones, mientras otro hilo del cliente pide
`GET /tareas` cada 50 ms. Se corrió con `HASH_MODE=bloqueante` (el hash dentro del loop,
sin executor) y con `HASH_MODE=executor`. Latencia en reposo: 1,0 ms.

| | Respuestas durante la tarea | Mediana | p95 | **Máxima** | Duración del hash |
|--|--|--|--|--|--|
| Sin executor | 7 | 2,0 ms | 2,3 ms | **2179,5 ms** | 2,19 s |
| Con executor | 50 | 1,4 ms | 1,9 ms | **2,6 ms** | 2,24 s |

**Interpretación.** Sin executor, la latencia máxima (2179 ms) coincide con la duración
de la tarea (2,19 s): el `GET` que llegó al empezar el hash esperó a que terminara, porque
el loop estuvo **congelado** y ninguna corrutina avanzó. Con executor, la máxima es de
2,6 ms, prácticamente la de reposo: el cálculo corre en un proceso hijo y el loop queda
libre. La cantidad de respuestas (7 contra 50) refleja lo mismo.

Dos detalles al leer la tabla. La **mediana y el p95 sin executor engañan**: con solo 7
muestras, una sola respuesta bloqueada no aparece en el p95, así que la métrica que
cuenta es la máxima. Y el **executor no acelera la tarea** (2,19 s contra 2,24 s: la
diferencia es el costo de enviar las tandas al proceso hijo); lo que garantiza es que la
API siga respondiendo.

### 4.3 Techo del pool

`python3 mediciones/medicion_techo.py --dur 0.2`: se lanzan N tareas `esperar` de 0,2 s y
se compara el tiempo total con el ideal, ⌈N / WORKERS⌉ × 0,2 s.

**Con 3 workers** (máximo teórico: 3 / 0,2 = 15 tareas/s)

| N | aceptadas | rechazadas | total (s) | ideal (s) | eficiencia | tareas/s | GET p95 (ms) |
|---|---|---|---|---|---|---|---|
| 10 | 10 | 0 | 0,83 | 0,80 | 96 % | 12,1 | 1,8 |
| 100 | 100 | 0 | 6,95 | 6,80 | 98 % | 14,4 | 2,3 |
| 500 | 500 | 0 | 33,74 | 33,40 | 99 % | 14,8 | 2,3 |
| 1100 | 1018 | **82** | 68,56 | 68,00 | 99 % | 14,8 | 2,6 |

**Con 50 workers y `QUEUE_MAXSIZE=20000`** (máximo teórico: 50 / 0,2 = 250 tareas/s)

| N | aceptadas | rechazadas | total (s) | ideal (s) | eficiencia | tareas/s | GET p95 (ms) |
|---|---|---|---|---|---|---|---|
| 100 | 100 | 0 | 0,51 | 0,40 | 79 % | 196,7 | 1,9 |
| 1000 | 1000 | 0 | 4,11 | 4,00 | 97 % | 243,3 | 2,5 |
| 5000 | 5000 | 0 | 20,39 | 20,00 | 98 % | 245,2 | 4,7 |
| 10000 | 10000 | 0 | 40,71 | 40,00 | 98 % | 245,6 | 6,6 |

Con 10.000 tareas en memoria, `docker stats` marcó ≈ 60 MiB en el contenedor de la API.

**Interpretación.**

1. **El techo de throughput es `WORKERS / duración`, y escala linealmente.** Con 3 workers
   se midieron 14,8 tareas/s y con 50, 245,6: la relación (≈ 16,6×) es casi exactamente
   50/3. El event loop no es el cuello de botella en este escenario.
2. **La eficiencia del 79 % con N=100 no es una degradación.** Son 2 rondas de 0,2 s (0,4 s
   ideales) y tardó 0,51 s: el ~0,1 s de diferencia es un costo fijo (envío de los `POST`
   y consulta cada 0,1 s) que pesa mucho en una corrida corta y no se nota en una de 40 s.
3. **El límite que sí apareció es la cola.** Con la cola de 1000, en N=1100 hubo 82
   rechazos (503). Probablemente las 1018 aceptadas sean 1000 de la cola, 3 en los
   workers y unas 15 que se consumieron mientras se seguía enviando, aunque no lo
   verifiqué. El servidor se protege en vez de aceptar sin límite.
4. **La API siguió ágil bajo carga:** el `POST` quedó en ≈ 1 ms y el `GET` en pocos
   milisegundos, porque las tareas ceden el control en cada `await`.
5. **Única señal de degradación: `GET /estadisticas` pasó de 1,9 a 6,6 ms** al crecer N.
   *Hipótesis (no verificada):* `/estadisticas` recorre todas las tareas guardadas, así que
   su costo crece con la cantidad acumulada, y como corre en el event loop retrasa un
   poco al resto. El diccionario de tareas nunca se purga.

**Lo que no se midió:** el punto donde algo falla de verdad. Con más carga (decenas de miles
de tareas, o tareas `descargar` con muchas URLs) los candidatos serían el tiempo de
`/estadisticas`, la memoria y, en descargas, el límite de conexiones y de descriptores de
archivo. Es una estimación, no un resultado.

---

## 5. Conceptos del curso aplicados

**Sockets TCP y servidores concurrentes (clases 13-14).** uvicorn abre un socket TCP en el
puerto 8000 y atiende a los clientes; `httpx` abre sockets TCP hacia los servidores de
descarga. A diferencia de los servidores de las clases 13-14, que atendían cada cliente con
un hilo o un proceso, acá un solo hilo atiende a todos. El `host="0.0.0.0"` hace que el
socket escuche en todas las interfaces, necesario para que el mapeo `8000:8000` de Docker
llegue al contenedor. *Dónde:* `uvicorn.run(...)` en `src/main.py` y `ports` en
`docker-compose.yml`.

**Productor–consumidor (clase 11).** `POST` produce ids y los workers los consumen de la
`asyncio.Queue`. Es el mismo patrón que con threads, pero con corrutinas: no hace falta
`Lock`, porque el event loop no interrumpe a una corrutina entre `await`s. *Dónde:*
`encolar()` (productor) y `_worker()` (consumidor) en `src/motor.py`.

**I/O multiplexing (clase 17).** El event loop espera eventos de muchos sockets a la vez
con `epoll`/`select` y despierta a la corrutina cuyo socket está listo. Es la razón por la
que 20 descargas caben en un solo hilo (medición 4.1). *Dónde:* cualquier `await` sobre red,
como `client.get(url)` en `_descargar_una()`.

**Generadores y corrutinas (clase 18).** Una corrutina es un generador que cede el control
en cada `await`. Un detalle que lo muestra: el `lifespan` de FastAPI es un generador
asíncrono con un `yield` que parte el código en "arranque" (antes) y "apagado" (después).
*Dónde:* `lifespan()` en `src/main.py`.

**Tareas del event loop (clases 20-21).** `asyncio.create_task` agenda una corrutina para
que corra concurrentemente; la `Task` resultante se puede cancelar de forma independiente.
Por eso cada trabajo tiene su propia `Task`, separada de la del worker. *Dónde:*
`_ejecutar()` en `src/motor.py`.

**Cancelación y timeouts (clase 21).** La cancelación en asyncio es **cooperativa**: `cancel()`
no mata nada a la fuerza, sino que lanza `CancelledError` en el próximo `await` de la tarea.
`wait_for` implementa el timeout con ese mismo mecanismo. *Dónde:* `cancelar()` y
`_ejecutar()` en `src/motor.py`.

**`concurrent.futures`, procesos y GIL (clase 22).** `hashear` usa un `ProcessPoolExecutor`
a través de `run_in_executor`: procesos y no threads, porque el GIL impide que dos threads
ejecuten bytecode de Python en paralelo. *Dónde:* `_hashear()` y `iniciar()` en
`src/motor.py`.

**Procesos hijos, `fork` y `spawn`.** En Linux (y dentro de Docker) el pool crea sus
procesos con `fork`; en macOS y Windows con `spawn`, que reimporta el módulo. Por eso el
arranque está bajo `if __name__ == "__main__"` y el pool se crea en el `lifespan`, no al
importar. *Dónde:* final de `src/main.py` e `iniciar()` en `src/motor.py`.

**Comunicación entre procesos (IPC).** El executor manda los argumentos al proceso hijo y
recibe el resultado por mecanismos de IPC (internamente, pipes), y para eso los serializa
con `pickle`. Por eso `hash_tanda` es una función a nivel de módulo y sus argumentos son
tipos simples (`bytes` e `int`). *Dónde:* `hash_tanda()` en `src/motor.py`.

**Señales.** `SIGTERM` y `SIGINT` provocan el apagado ordenado (uvicorn las captura y
dispara el cierre del `lifespan`); `SIGKILL` no se puede atrapar, por eso `stop_grace_period`
debe superar a `SHUTDOWN_GRACE`. En Docker, `python` es el PID 1 y recibe la señal
directamente (sin shell intermedio). *Dónde:* `detener()` en `src/motor.py` y `Dockerfile`.

**Procesos zombis y `wait`.** Al apagar, `pool.shutdown(wait=True)` espera a los procesos
hijos y los recoge, en lugar de dejarlos huérfanos o zombis. Se ejecuta con
`asyncio.to_thread` para no bloquear el loop. *Dónde:* `detener()` en `src/motor.py`.

**Race conditions y `Lock`.** Las condiciones de carrera aparecen cuando dos flujos
modifican un dato compartido con operaciones que se pueden intercalar. Acá todo el motor
corre en un solo hilo y el loop solo cambia de corrutina en un `await`, así que una
secuencia sin `await` en el medio es atómica y no hace falta `Lock`. *Dónde:* cualquier
modificación de `self.tareas` o `self.ocupados`, siempre sin `await` entre la lectura y la
escritura.

**Context managers y decoradores (Bloque 0).** `async with` garantiza que el cliente HTTP
se cierre aun si la tarea se cancela; `@asynccontextmanager` define el `lifespan`;
`@app.get/post/delete` registran las rutas. *Dónde:* `descargar()` en `src/motor.py` y
`src/main.py`.

**HTTP y FastAPI (clase 19).** Se responde `202 Accepted` para trabajo diferido (el
`POST` no espera a que la tarea termine), `404`, `422` (validación con Pydantic) y `503`
(cola llena o apagado). *Dónde:* los endpoints en `src/main.py`.

**Contrapresión (backpressure).** Una cola acotada obliga al productor a frenar cuando el
consumidor no da abasto: acá `put_nowait` sobre una cola de tamaño máximo responde 503 en
lugar de acumular sin límite. *Dónde:* `encolar()` en `src/motor.py` y `QUEUE_MAXSIZE`.

---

## 6. Limitaciones conocidas

- **El estado vive en memoria.** Se pierde si el proceso muere sin recibir `SIGTERM`
  (por ejemplo con `SIGKILL`). El volcado se reporta al arrancar pero **no se recarga**.
- **`tareas` crece sin límite:** no se purgan tareas viejas, lo que aumenta la memoria y
  el costo de `/estadisticas` y de `GET /tareas`.
- **Un worker atiende una tarea a la vez.** Un `descargar` con muchas URLs ocupa un worker
  entero, y la concurrencia entre tareas está limitada por `WORKERS`.
- **Una tarea `pendiente` cancelada** sigue ocupando un lugar en la cola hasta que un
  worker la descarta.
- **Cancelar un `hashear` no es instantáneo:** termina la tanda en curso, que dura
  decenas de milisegundos.
- **El timeout no funciona en `HASH_MODE=bloqueante`**, porque el loop está congelado.
  Ese modo existe solo para la medición 2.
- **El rechazo durante el apagado es parcial:** `aceptando = False` devuelve 503, pero
  uvicorn deja de aceptar conexiones primero, así que en la práctica el cliente ve la
  conexión rechazada antes de llegar a ese 503.
- **El volcado a JSON es E/S síncrona** (ocurre al apagar, cuando ya no se atiende a nadie).
- **No hay autenticación ni límite por cliente.**
- Las mediciones se hicieron en una sola máquina, con cliente y servidor juntos, y no
  se repitieron varias veces para obtener un intervalo de confianza.

---

## 7. Lo que aprendí

Lo que más me costó fue entender qué es realmente cada objeto de asyncio. En mi primera
versión guardaba `asyncio.current_task()` pensando que era "la tarea", pero ese objeto era
la corrutina del **worker**, no la del trabajo. Al cancelarla con `DELETE`, mataba al
worker entero, y después de tantas cancelaciones como workers había, el sistema dejaba de
procesar sin avisar. Entendí que cancelar "una tarea" y cancelar "a quien la ejecuta" son
cosas distintas, y que para separarlas hay que darle al trabajo su propia `asyncio.Task`.
Un problema parecido me enseñó que una excepción no capturada dentro de un worker lo
mata en silencio y deja la tarea en `ejecutando` para siempre.

Las mediciones me hicieron ver con números algo que antes era solo teoría. Esperaba que
bloquear el event loop fuera malo, pero no pensé que la latencia máxima iba a coincidir
casi exacto con la duración de la tarea (2179 ms contra 2,19 s): mientras una corrutina no
hace `await`, el servidor entero está sordo. También me llamó la atención que el
executor no hizo la tarea más rápida (2,24 s contra 2,19 s): no mejora la velocidad del
cálculo, lo que garantiza es que la API siga respondiendo. Y en la medición de I/O vi la
diferencia entre concurrencia y paralelismo: 20 descargas en un solo hilo tardaron 2 s
y no 40, no porque se ejecutaran en paralelo, sino porque el hilo no se quedaba esperando.

Otra cosa que aprendí es que concurrencia dentro de una tarea y concurrencia entre tareas
son límites distintos: el `gather` no tiene tope, pero el pool sí, y por eso 20 tareas
separadas con 3 workers solo lograron un speedup de 2,8×. Además, hacer que el apagado sea
ordenado me obligó a pensar en el orden de las cosas (dejar de aceptar, esperar, cancelar,
cerrar el pool, volcar) y en cómo Docker manda `SIGTERM` y después `SIGKILL`.