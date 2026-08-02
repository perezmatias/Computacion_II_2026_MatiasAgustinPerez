# TP1 — Monitor de Procesos y Threads

**Computación II — Universidad de Mendoza — 2026**
**Alumno:** Matías Agustín Pérez

---

## 1. Descripción general

Este proyecto es un monitor de procesos en tiempo real para Linux, similar en espíritu a `htop`,
pero con foco en mostrar la **anatomía interna** de cada proceso (memoria, file descriptors,
threads, señales, scheduling) leyendo directamente el filesystem virtual `/proc`, sin usar
`psutil` ni herramientas equivalentes.

El sistema está compuesto por **8 procesos independientes** que corren en paralelo:
un recolector que lista los PIDs activos, 7 analizadores especializados (cada uno mira una
dimensión distinta del sistema) y una interfaz de texto (TUI) construida con `curses` que
muestra los datos y permite navegar, filtrar, ordenar y ajustar el refresco de cada vista
en caliente.

### Cómo correrlo

```bash
cd Tp1
docker compose run --rm monitor
```

> ⚠️ **Importante**: se usa `docker compose run --rm monitor`, **no** `docker compose up --build`.
> El motivo está explicado en la sección [Limitaciones conocidas](#6-limitaciones-conocidas).

Si preferís correrlo directo en tu máquina (sin Docker, requiere Linux):

```bash
cd Tp1/src
python3 main.py
```

### Controles

| Tecla | Acción |
|---|---|
| `1`–`8` | Cambiar de vista (Resumen, Memoria, FDs, Sistema, Threads, Señales, Scheduling, Global) |
| `↑` / `↓` | Navegar la lista de procesos |
| `Enter` | Fijar (pin) el proceso seleccionado en el tope de la lista |
| `/` | Filtrar por nombre de proceso |
| `u` | Filtrar por usuario |
| `c` | Alternar orden (PID → CPU% → RSS → PID...) |
| `+` / `-` | Ajustar el intervalo de refresco de la vista activa |
| `h` / `?` | Ayuda |
| `q` | Salir |

---

## 2. Diagrama de arquitectura
┌─────────────────────────┐
                     │       RECOLECTOR         │
                     │  os.listdir('/proc')     │
                     │  cada 2s (fijo)          │
                     └────────────┬─────────────┘
                                  │ reparte lista de PIDs
                ┌─────────────────┼──────────────────────┬── ... (7 colas)
                ▼                 ▼                      ▼
          Queue(resumen)   Queue(memoria)          Queue(scheduling)
                │                 │                      │
                ▼                 ▼                      ▼
     ┌──────────────────┐ ┌──────────────┐      ┌──────────────────┐
     │ ANALIZADOR        │ │ ANALIZADOR   │ ...  │ ANALIZADOR        │
     │ resumen.py         │ │ memoria.py   │      │ scheduling.py     │
     │ (proceso propio)   │ │ (proceso)    │      │ (proceso)         │
     └─────────┬──────────┘ └──────┬───────┘      └─────────┬─────────┘
               │                    │                        │
               └────────────┬───────┴────────────────────────┘
                            ▼
              ┌───────────────────────────────┐
              │     SNAPSHOT GLOBAL             │
              │  multiprocessing.Manager().dict()│
              │  { 'resumen': {...},             │
              │    'memoria': {...},             │
              │    'fds': {...}, ... }           │
              └───────────────┬───────────────┘
                              │ lee
                              ▼
                    ┌─────────────────┐
                    │   TUI (curses)   │◄── multiprocessing.Value (intervalos, uno por vista)
                    │  proceso main    │      escritos por la TUI con +/-, leídos por analizadores
                    └─────────────────┘
                    analizador "sistema_global" (CPU/mem/load del sistema completo, no usa cola de PIDs)
señales al proceso main (SIGINT/TERM/HUP/USR1) manejadas en main.py
**Procesos que corren simultáneamente**: recolector + 7 analizadores + proceso principal (TUI) = **9 procesos**.

---

## 3. Decisiones de diseño

### ¿Por qué `Manager().dict()` para el snapshot global y no `Value`/`Array`?

`Value` y `Array` solo pueden compartir **tipos primitivos de C** (enteros, floats, bytes) en
bloques de memoria de tamaño fijo. El snapshot global necesita guardar estructuras heterogéneas
y de tamaño variable: diccionarios anidados, listas de threads por proceso, listas de FDs con
su destino y tipo, listas de nombres de señales decodificadas, etc. Para eso se necesita un
objeto Python completo compartido entre procesos, y la única herramienta de `multiprocessing`
que lo permite es `Manager`, que levanta un proceso servidor aparte y expone un proxy sincronizado
sobre el dict real.

El costo es que `Manager` es más lento que `Value`/`Array` (cada acceso implica IPC hacia el
proceso servidor), pero como cada analizador escribe su propia clave del diccionario
(`snapshot_global['memoria']`, `snapshot_global['fds']`, etc.) y nadie más escribe esa misma
clave, no hay condición de carrera entre analizadores: cada uno tiene su "carril" propio dentro
del dict compartido.

### ¿Por qué `multiprocessing.Value` para los intervalos de refresco?

Acá sí conviene `Value` en lugar de `Manager`: el intervalo de cada vista es un solo `float`,
se lee muy frecuentemente (cada iteración del loop de cada analizador) y se escribe rara vez
(solo cuando el usuario aprieta `+`/`-` o llega SIGHUP). Usar `Manager` para esto sería pagar el
costo de IPC del proceso servidor por algo que es un caso perfecto para memoria compartida
directa. Cada vista tiene su propio `Value('d', ...)`, protegido con `get_lock()` cuando se
escribe desde la TUI, para evitar que una escritura quede a mitad de camino si en algún momento
se agregara otro escritor.

Esto también es lo que permite que **SIGHUP recargue los intervalos en caliente**: como el
analizador lee `intervalo_compartido.value` en cada vuelta de su loop (no en un argumento fijo
al crear el proceso), cambiar ese `Value` desde el manejador de SIGHUP en el proceso principal
se refleja inmediatamente en el comportamiento del analizador, sin reiniciar nada.

### ¿Por qué `Queue` para distribuir PIDs del recolector a los analizadores?

Cada analizador necesita la lista de PIDs actuales para saber qué procesos inspeccionar, pero
cada uno trabaja a su propio ritmo (por ejemplo, señales y scheduling refrescan cada 10s por
defecto, mientras que resumen y sistema lo hacen cada 2s). Usar una `Queue` por analizador
desacopla al recolector de la velocidad de cada consumidor: el recolector simplemente publica
la lista de PIDs en las 7 colas cada 2 segundos, y cada analizador la consume cuando su propio
loop lo necesita (`if not cola_in.empty(): pids = cola_in.get()`).

**Limitación conocida de este diseño**: el recolector siempre corre a un intervalo fijo de 2s,
independientemente de que alguna vista pida refrescos más rápidos (mínimo 0.5s para Resumen/
Sistema/Threads). Esto significa que, en el peor caso, un analizador con intervalo de 0.5s puede
estar reprocesando la misma lista de PIDs varias veces antes de que el recolector publique una
lista nueva. No es incorrecto (los datos igual se recalculan con el `/proc` más reciente en cada
vuelta), pero es una simplificación: idealmente el recolector debería adaptarse al intervalo
mínimo de las vistas activas.

### ¿Cómo se evitan las race conditions?

- **Entre analizadores**: cada uno escribe una clave distinta del `Manager().dict()`, así que
  nunca hay dos procesos escribiendo la misma entrada al mismo tiempo.
- **En los intervalos compartidos**: se usa `intervalo.get_lock()` al escribir desde la TUI
  (tanto en el manejo de `+`/`-` como en el manejador de SIGHUP), aunque en la práctica solo
  hay un escritor (el proceso de la TUI) — el lock queda como buena práctica ante un futuro
  segundo escritor.
- **Dentro de cada analizador**: el cálculo de CPU% (tanto por proceso en `sistema.py` como
  por thread en `threads.py`) guarda un diccionario `lecturas_previas` con la última medición
  de jiffies, **local a ese proceso** (no compartido), para poder calcular el delta entre dos
  lecturas consecutivas sin interferencia de otros procesos.

### ¿Por qué separar "sistema" (por proceso) de "sistema_global" (del SO completo)?

Son conceptualmente distintos: uno describe el estado y CPU% de *cada proceso* leyendo
`/proc/<pid>/stat`, el otro agrega estadísticas de *todo el sistema* leyendo `/proc/stat`,
`/proc/meminfo` y `/proc/loadavg`, sin necesitar la lista de PIDs en absoluto. Por eso
`sistema_global.py` tiene una firma distinta a los demás analizadores: no recibe una `Queue`
de entrada, porque no necesita saber qué PIDs existen para hacer su trabajo.

### ¿Por qué no se usó `fork`/`spawn` explícito?

No se llamó a `multiprocessing.set_start_method(...)`, por lo que la aplicación usa el método
por defecto de la plataforma. En Linux (que es el entorno de ejecución exigido por la consigna,
vía Docker) el default es `fork`, que es el más rápido y el que permite que los procesos hijos
hereden el estado del padre sin re-importar módulos. Como el proyecto no está pensado para
correr en Windows/macOS, no se justificó pagar el costo de `spawn` solo por portabilidad.

---

## 4. Conceptos del curso aplicados

- **Clase 3 (Procesos - Fundamentos)**: toda la lectura de `/proc/<pid>/stat`, `/proc/<pid>/status`
  y `/proc/<pid>/maps` (indirectamente, para segmentos de memoria) se apoya en entender la
  anatomía del proceso vista en esta clase. El estado `Z` (zombie) que se cuenta en
  `sistema_global.py` (`conteo.get('Z', 0)`) es el mismo concepto de zombie visto acá y
  profundizado en la clase siguiente.

- **Clase 4 (fork, exec, wait)**: el campo de estado `Z` en `/proc/<pid>/stat` representa
  exactamente lo que se vio en esta clase: un proceso que terminó pero cuyo padre todavía no
  llamó a `wait()`/`waitpid()`. La vista Sistema Global cuenta cuántos zombies hay en todo el
  sistema en un momento dado.

- **Clase 6 (Señales)**: `main.py` registra manejadores para SIGINT (implícito, vía
  `KeyboardInterrupt` capturado en el `try/finally`), SIGTERM, SIGHUP y SIGUSR1. El manejador
  de SIGTERM (`manejador_shutdown`) simplemente levanta `KeyboardInterrupt` para reusar el mismo
  camino de limpieza que SIGINT, en vez de duplicar lógica.

  **Nota honesta**: el manejador de SIGUSR1 (`manejador_dump`) hace `json.dump()` a un archivo
  directamente dentro del handler. Esto **no es estrictamente async-signal-safe** en el sentido
  clásico visto en la clase (operaciones de I/O con buffering, serialización, no están en la
  lista de funciones seguras para un manejador de señal en C). En la práctica funciona porque
  el modelo de señales de Python es distinto al de C: el intérprete solo ejecuta el código
  Python del handler entre instrucciones de bytecode, no lo interrumpe verdaderamente en medio
  de una operación como haría un handler de señal de C a nivel de kernel. Aun así, un diseño
  más purista habría usado el patrón *self-pipe* (visto también en clase 6) para solo marcar
  un flag desde el handler y hacer el trabajo pesado (el dump a JSON) en el loop principal.
  Se optó por la versión simple por tiempo, documentando la diferencia acá.

- **Clases 8 y 9 (Multiprocessing fundamentos y avanzado)**: es el corazón de la arquitectura.
  Se usan `Process` para cada analizador, `Queue` para distribuir trabajo del recolector,
  `Manager().dict()` para el snapshot compartido de estructuras complejas, y `Value` (con
  `get_lock()`) para los intervalos de refresco — exactamente la distinción que se vio en
  clase 9 entre "`Value`/`Array` para datos simples y rápidos" vs "`Manager` para estructuras
  Python complejas y flexibles".

- **Clase 10 (Threading / GIL)**: deliberadamente **no se usaron threads** para la arquitectura
  principal, tal como pide la consigna. La TUI usa `stdscr.nodelay(True)` para hacer polling
  no bloqueante del teclado dentro de un único proceso, en vez de un thread aparte para la
  entrada — la consigna permitía usar un thread para esto, pero no era necesario dado que
  `curses` ya ofrece un modo no bloqueante nativo.

---

## 5. Cómo correr y testear

### Requisitos

- Docker y Docker Compose (probado con Docker 29.1.3 / Compose 2.40.3)
- Linux como sistema operativo del host o de la VM que corre Docker (el proyecto lee `/proc`,
  que no existe en macOS/Windows fuera de una VM Linux)

### Levantar el monitor

```bash
cd Tp1
docker compose run --rm monitor
```

### Probar las señales del monitor

Necesitás el PID del proceso `main.py` **dentro** del contenedor. En otra terminal:

```bash
docker compose exec monitor sh -c "ps aux | grep main.py"
docker compose exec monitor kill -USR1 <PID>   # genera dump_estado.json
docker compose exec monitor kill -HUP <PID>    # recarga config.json en caliente
docker compose exec monitor kill -TERM <PID>   # shutdown limpio (igual a Ctrl+C)
```

El archivo `dump_estado.json` se genera dentro de `Tp1/` (queda visible en el host gracias al
volumen montado en `docker-compose.yml`).

### Probar la recarga de configuración (SIGHUP)

1. Con el monitor corriendo, andá a la vista `2` (Memoria) y fijate el intervalo mostrado
   arriba a la derecha (`Refresco: 3.0s`).
2. Editá `config.json` y cambiá `"intervalo_memoria": 3.0` por otro valor, por ejemplo `8.0`.
3. Desde otra terminal, mandá `kill -HUP <PID>`.
4. El número de "Refresco" en pantalla debería cambiar sin reiniciar el monitor.

---

## 6. Limitaciones conocidas

- **`docker compose up --build` no funciona para esta aplicación** (queda "trabada" mostrando
  solo los primeros `print()` de arranque). La causa es que Compose multiplexa/bufferiza la
  salida estándar de los contenedores línea por línea para poder combinar logs de varios
  servicios con prefijo (`monitor-1  |`), y ese procesamiento rompe las secuencias de escape
  que `curses` necesita para dibujar pantalla completa. Se confirmó que **no** es un problema
  del código de la aplicación (`curses` fue probado de forma aislada dentro del contenedor con
  `python3 -c "import curses; curses.wrapper(lambda s: None)"` y funcionó sin errores) y que
  el problema desaparece completamente usando `docker compose run --rm monitor`, que conecta
  la terminal directamente al contenedor sin pasar por el sistema de logs agregados. Probado
  con Docker Compose 2.40.3 y Docker 29.1.3; no se investigó si versiones más nuevas de Compose
  resuelven esto.

- **Falta implementar SIGUSR2** (toggle de modo verbose). Están implementadas SIGINT, SIGTERM,
  SIGHUP y SIGUSR1, pero no SIGUSR2. Queda como pendiente.

- **SIGWINCH** (repintado ante resize de terminal) no está implementado. La consigna lo marca
  como opcional/recomendado, no obligatorio.

- **El recolector tiene un intervalo fijo de 2 segundos**, sin adaptarse dinámicamente al
  intervalo mínimo configurado en las vistas activas (ver detalle en la sección de decisiones
  de diseño, punto sobre `Queue`).

- **Sin sincronización explícita entre el recolector y los analizadores más allá de la `Queue`
  misma**: si un analizador es mucho más lento que el intervalo del recolector, la cola puede
  acumular listas de PIDs no consumidas. No se observaron problemas de memoria en pruebas
  cortas, pero no se testeó el comportamiento en ejecuciones de larga duración (horas) ni con
  cientos de procesos simultáneos en el sistema.

- **Los FDs y threads con detalle completo (`readlink` por FD, lectura de `/proc/<pid>/task/<tid>/...`
  por thread) son más costosos que un simple conteo.** Para procesos con muchos FDs o threads
  (por ejemplo, un navegador con cientos de FDs), esto puede introducir latencia perceptible en
  esas dos vistas específicas — mitigado parcialmente por tener intervalos de refresco más
  altos por defecto (5s para FDs, 2s para threads) que las vistas más livianas.

- **No se probó en sistemas con miles de procesos activos** ni se midió el uso de memoria del
  proceso `Manager` bajo esa carga.

---

## 7. Decisiones sobre la TUI

Se usó `curses` (biblioteca estándar de Python, sin dependencias externas) en lugar de `rich`.
La interfaz se organiza en una única función de render (`dibujar_interfaz` en `tui.py`) con un
loop principal que:

1. Calcula `altura`/`ancho` de la terminal al inicio de cada vuelta (necesario para que la
   navegación con flechas sepa cuántas filas entran en pantalla antes de hacer scroll).
2. Lee una tecla de forma no bloqueante (`stdscr.nodelay(True)`).
3. Redibuja toda la pantalla según la vista activa, leyendo directamente del
   `snapshot_global` compartido (sin copiar datos a estructuras locales).
4. Duerme 0.1s antes de la siguiente vuelta, para no consumir CPU en un loop apretado
   mientras espera input.

Las 7 vistas de procesos (todas menos la vista `8`, Sistema Global) comparten una única tabla
base con columnas PID/Usuario/Nombre + una columna "Detalle" que cambia de contenido según la
vista activa. Esto permite que filtro, orden y pin funcionen de forma consistente sin importar
qué vista esté mirando el usuario, en vez de tener 7 tablas completamente distintas con lógica
de filtrado duplicada en cada una.

---

## 8. Lo que aprendí

*(Sección pendiente de completar — reflexión personal sobre el proceso de desarrollo)*