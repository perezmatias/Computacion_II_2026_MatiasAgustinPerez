# TP1

**Computación II — Universidad de Mendoza — 2026**
**Alumno:** Matías Agustin Perez

---

## Índice

1. [Descripción general](#1-descripción-general)
2. [Diagrama de arquitectura](#2-diagrama-de-arquitectura)
3. [Decisiones de diseño](#3-decisiones-de-diseño)
4. [Conceptos del curso aplicados](#4-conceptos-del-curso-aplicados)
5. [Cómo correr y testear](#5-cómo-correr-y-testear)
6. [Limitaciones conocidas](#6-limitaciones-conocidas)
7. [Decisiones sobre la TUI](#7-decisiones-sobre-la-tui)
8. [Lo que aprendí](#8-lo-que-aprendí)

---

## 1. Descripción general

Este proyecto es un monitor de procesos en tiempo real para Linux, similar en espíritu a `htop`,
pero con foco en mostrar la **anatomía interna** de cada proceso (memoria, file descriptors,
threads, señales, scheduling) leyendo directamente el filesystem virtual `/proc`, sin usar
`psutil` ni herramientas equivalentes.

El sistema está compuesto por **9 procesos independientes** que corren en paralelo: un
recolector que lista los PIDs activos, 7 analizadores especializados (cada uno mira una
dimensión distinta del sistema) y una interfaz de texto (TUI) construida con `curses` que
muestra los datos y permite navegar, filtrar, ordenar y ajustar el refresco de cada vista
en caliente. Un octavo "analizador" (sistema global) no depende de PIDs y agrega estadísticas
de todo el sistema, incluyendo el top 3 de procesos por CPU% y por memoria.

### Cómo correrlo

```bash
docker compose run --rm monitor
```

> ⚠️ **Importante**: se usa `docker compose run --rm monitor`, **no** `docker compose up --build`.
> El motivo está explicado en [Limitaciones conocidas](#6-limitaciones-conocidas).

Si preferís correrlo directo en tu máquina (sin Docker, requiere Linux):

```bash
cd src
python3 main.py
```

### Controles

| Tecla | Acción |
|---|---|
| `1`–`8` | Cambiar de vista (Resumen, Memoria, FDs, Sistema/Estado, Threads, Señales, Scheduling, Global) |
| `↑` / `↓` | Navegar la lista de procesos |
| `Enter` | Fijar (pin) el proceso seleccionado en el tope de la lista |
| `/` | Filtrar por nombre de proceso |
| `u` | Filtrar por usuario |
| `c` | Alternar orden (PID → CPU% → RSS → PID...) |
| `+` / `-` | Ajustar el intervalo de refresco de la vista activa |
| `h` / `?` | Ayuda |
| `q` | Salir |

### Modo verbose (SIGUSR2)

Además de la navegación por teclado, el monitor responde a `SIGUSR2` para alternar un
**modo verbose** que agrega más detalle por proceso en cada vista (comando completo,
más campos de memoria, FDs individuales, hilos individuales, etc.):

```bash
docker compose exec monitor sh -c "ps aux | grep main.py"
docker compose exec monitor kill -USR2 <PID>
```

Cuando está activo, aparece la palabra `VERBOSE` en la barra de estado de la TUI.

---

## 2. Diagrama de arquitectura

```
                     ┌──────────────────────────┐
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
                              │ lee (y también lee cruzado top3 CPU/mem)
                              ▼
                    ┌─────────────────┐
                    │   TUI (curses)   │◄── multiprocessing.Value (intervalos, uno por vista)
                    │  proceso main    │      escritos por la TUI con +/-, leídos por analizadores
                    └─────────────────┘      ◄── multiprocessing.Value (modo_verbose)
                                                  escrito por el handler de SIGUSR2, leído por la TUI

    analizador "sistema_global" (CPU/mem/load/top3 del sistema completo, no usa cola de PIDs;
    lee 'sistema', 'memoria' y 'resumen' del snapshot para calcular el top3)

señales al proceso main (SIGINT/TERM/HUP/USR1/USR2) manejadas en main.py
```

**Procesos que corren simultáneamente**: recolector + 7 analizadores + proceso principal (TUI) = **9 procesos**.

---

## 3. Decisiones de diseño

### ¿Por qué `Manager().dict()` para el snapshot global y no `Value`/`Array`?

`Value` y `Array` solo pueden compartir **tipos primitivos de C** (enteros, floats, bytes) en
bloques de memoria de tamaño fijo. El snapshot global necesita guardar estructuras heterogéneas
y de tamaño variable: diccionarios anidados, listas de threads por proceso, listas de FDs con
su destino y tipo, listas de nombres de señales decodificadas, segmentos de memoria agrupados,
etc. Para eso se necesita un objeto Python completo compartido entre procesos, y la única
herramienta de `multiprocessing` que lo permite es `Manager`, que levanta un proceso servidor
aparte y expone un proxy sincronizado sobre el dict real.

El costo es que `Manager` es más lento que `Value`/`Array` (cada acceso implica IPC hacia el
proceso servidor), pero como cada analizador escribe su propia clave del diccionario
(`snapshot_global['memoria']`, `snapshot_global['fds']`, etc.) y nadie más escribe esa misma
clave, no hay condición de carrera entre analizadores: cada uno tiene su "carril" propio dentro
del dict compartido. El analizador `sistema_global` es el único que además *lee* claves ajenas
(`sistema`, `memoria`, `resumen`) para calcular el top 3 por CPU y por memoria — pero solo lee,
nunca escribe esas claves, así que sigue sin haber dos escritores para la misma clave.

### ¿Por qué `multiprocessing.Value` para los intervalos de refresco y el modo verbose?

Acá sí conviene `Value` en lugar de `Manager`: tanto el intervalo de cada vista (un `float`)
como el flag de modo verbose (un `int` 0/1) son datos primitivos, se leen muy frecuentemente
(cada iteración del loop de cada analizador, o cada refresco de la TUI) y se escriben rara vez
(solo cuando el usuario aprieta `+`/`-`, llega SIGHUP, o llega SIGUSR2). Usar `Manager` para
esto sería pagar el costo de IPC del proceso servidor por algo que es un caso perfecto para
memoria compartida directa. Cada vista tiene su propio `Value('d', ...)`, y el modo verbose
tiene un único `Value('i', 0)` global (afecta a todas las vistas por igual), protegidos con
`get_lock()` cuando se escribe, para evitar que una escritura quede a mitad de camino si en
algún momento se agregara otro escritor.

Esto también es lo que permite que **SIGHUP recargue los intervalos en caliente** y que
**SIGUSR2 alterne el modo verbose en caliente**: como el analizador (o la TUI) lee
`.value` en cada vuelta de su loop —no en un argumento fijo al crear el proceso—, cambiar
ese `Value` desde el manejador de la señal en el proceso principal se refleja inmediatamente
en el comportamiento, sin reiniciar nada.

### ¿Por qué `Queue` para distribuir PIDs del recolector a los analizadores?

Cada analizador necesita la lista de PIDs actuales para saber qué procesos inspeccionar, pero
cada uno trabaja a su propio ritmo (por ejemplo, señales y scheduling refrescan cada 10s por
defecto, mientras que resumen y sistema lo hacen cada 2s). Usar una `Queue` por analizador
desacopla al recolector de la velocidad de cada consumidor: el recolector simplemente publica
la lista de PIDs en las 7 colas cada 2 segundos, y cada analizador la consume cuando su propio
loop lo necesita (`if not cola_in.empty(): pids = cola_in.get()`).

**Limitación conocida de este diseño**: el recolector siempre corre a un intervalo fijo de 2s,
independientemente de que alguna vista pida refrescos más rápidos (mínimo 0.5s para Resumen/
Sistema/Threads). No es incorrecto (los datos igual se recalculan con el `/proc` más reciente
en cada vuelta), pero es una simplificación: idealmente el recolector debería adaptarse al
intervalo mínimo de las vistas activas.

### ¿Cómo se evitan las race conditions?

- **Entre analizadores**: cada uno escribe una clave distinta del `Manager().dict()`, así que
  nunca hay dos procesos escribiendo la misma entrada al mismo tiempo. El único analizador que
  lee claves ajenas (`sistema_global`, para el top 3) lo hace de forma de solo-lectura.
- **En los intervalos y el modo verbose compartidos**: se usa `.get_lock()` al escribir desde
  la TUI (tanto en el manejo de `+`/`-` como en el manejador de SIGHUP) y desde el manejador de
  SIGUSR2 en `main.py`, aunque en la práctica solo hay un escritor por cada `Value` — el lock
  queda como buena práctica ante un futuro segundo escritor.
- **Dentro de cada analizador**: el cálculo de CPU% (tanto por proceso en `sistema.py` como
  por thread en `threads.py`) guarda un diccionario `lecturas_previas` con la última medición
  de jiffies, **local a ese proceso** (no compartido), para poder calcular el delta entre dos
  lecturas consecutivas sin interferencia de otros procesos.

### ¿Por qué separar "resumen" (identidad) de "sistema" (estado/CPU%)?

La consigna agrupa esto en una sola vista "Resumen", pero se decidió separarlos en dos
analizadores y dos vistas (`1` y `4`) porque tienen ritmos de cambio distintos: el nombre,
usuario, PPID y comando de un proceso casi nunca cambian una vez que arrancó, mientras que el
estado y el CPU% cambian constantemente. Separarlos permite en principio ajustar intervalos
distintos para cada uno (aunque ambos usan el mismo default de 2s en la config actual). El
costo es que la TUI queda con 8 vistas en vez de las 7 de la tabla original de la consigna.
Esto no afecta el cumplimiento de los keybindings: la consigna pide `1–7 **o** r/m/f/t/s/p/g`
— es decir, una forma **u otra**, no ambas — así que usar los números `1`–`8` para las 8 vistas
cubre el requisito igual. No se implementaron además los atajos por letra porque no hay un
mapeo directo y sin ambigüedad de 7 letras a 8 vistas, y no hacía falta dado que la consigna ya
ofrece los números como alternativa válida.

### ¿Por qué separar "sistema" (por proceso) de "sistema_global" (del SO completo)?

Son conceptualmente distintos: uno describe el estado y CPU% de *cada proceso* leyendo
`/proc/<pid>/stat`, el otro agrega estadísticas de *todo el sistema* leyendo `/proc/stat`,
`/proc/meminfo` y `/proc/loadavg` — más el top 3 de procesos por CPU% y por memoria, derivado
cruzando los snapshots de `sistema`, `memoria` y `resumen`. Por eso `sistema_global.py` tiene
una firma distinta a los demás analizadores: no recibe una `Queue` de entrada, porque no
necesita saber qué PIDs existen para hacer su trabajo principal (solo los usa indirectamente
al leer el snapshot ya calculado por otros analizadores para el top 3).

### ¿Por qué no se usó `fork`/`spawn` explícito?

No se llamó a `multiprocessing.set_start_method(...)`, por lo que la aplicación usa el método
por defecto de la plataforma. En Linux (que es el entorno de ejecución exigido por la consigna,
vía Docker) el default es `fork`, que es el más rápido y el que permite que los procesos hijos
hereden el estado del padre sin re-importar módulos. Como el proyecto no está pensado para
correr en Windows/macOS, no se justificó pagar el costo de `spawn` solo por portabilidad.

---

## 4. Conceptos del curso aplicados

- **Clase 3 (Procesos - Fundamentos)**: toda la lectura de `/proc/<pid>/stat`, `/proc/<pid>/status`
  y `/proc/<pid>/maps` se apoya en entender la anatomía del proceso vista en esta clase. La
  vista Memoria agrupa `/proc/<pid>/maps` por segmento (`heap`, `stack`, `text`, `data`,
  `shared`), que es exactamente la división texto/datos/heap/stack de memoria virtual vista en
  clase. El estado `Z` (zombie) que se cuenta en `sistema_global.py` es el mismo concepto de
  zombie visto acá y profundizado en la clase siguiente.

- **Clase 4 (fork, exec, wait)**: el campo de estado `Z` en `/proc/<pid>/stat` representa
  exactamente lo que se vio en esta clase: un proceso que terminó pero cuyo padre todavía no
  llamó a `wait()`/`waitpid()`. La vista Sistema Global cuenta cuántos zombies hay en todo el
  sistema en un momento dado. El campo PPID (leído ahora en `resumen.py` desde
  `/proc/<pid>/status: PPid`) es la base para reconstruir la jerarquía padre-hijo que se estudia
  en esta clase con `fork()`.

- **Clase 5 (Pipes / FDs)**: la vista File Descriptors lista `/proc/<pid>/fd/`, resuelve cada
  symlink con `os.readlink()` y clasifica el destino (socket, pipe, tty, device, file) según el
  patrón del string — el mismo mecanismo por el cual el shell resuelve `stdin`/`stdout`/`stderr`
  como FDs 0/1/2 vistos en clase.

- **Clase 6 (Señales)**: `main.py` registra manejadores para SIGINT (implícito, vía
  `KeyboardInterrupt` capturado en el `try/finally`), SIGTERM, SIGHUP, SIGUSR1 y **SIGUSR2**.
  El manejador de SIGTERM (`manejador_shutdown`) simplemente levanta `KeyboardInterrupt` para
  reusar el mismo camino de limpieza que SIGINT, en vez de duplicar lógica. El manejador de
  SIGUSR2 (`manejador_verbose`) es deliberadamente mínimo — solo invierte un entero en memoria
  compartida bajo lock — siguiendo el principio de que un handler de señal debe hacer el mínimo
  trabajo posible; todo el trabajo "pesado" (decidir qué mostrar distinto) queda en el loop
  principal de la TUI, que lee el flag en cada vuelta.

  La vista Señales decodifica las máscaras hexadecimales de 64 bits (`SigPnd`, `ShdPnd`,
  `SigBlk`, `SigIgn`, `SigCgt`) bit a bit contra `signal.Signals`, distinguiendo señales
  **pendientes del proceso** (`SigPnd`) de **pendientes del grupo de procesos** (`ShdPnd`) —
  esta última se agregó para reflejar la diferencia entre señal dirigida a un PID puntual vs.
  señal dirigida a todo un grupo (`kill -SIGNAL -PGID`), concepto visto en clase junto con
  sesiones y grupos de procesos.

  **Nota honesta**: el manejador de SIGUSR1 (`manejador_dump`) hace `json.dump()` a un archivo
  directamente dentro del handler. Esto **no es estrictamente async-signal-safe** en el sentido
  clásico visto en la clase (operaciones de I/O con buffering, serialización, no están en la
  lista de funciones seguras para un manejador de señal en C). En la práctica funciona porque
  el modelo de señales de Python es distinto al de C: el intérprete solo ejecuta el código
  Python del handler entre instrucciones de bytecode, no lo interrumpe verdaderamente en medio
  de una operación como haría un handler de señal de C a nivel de kernel. Aun así, un diseño
  más purista habría usado el patrón *self-pipe* (visto también en clase 6) para solo marcar
  un flag desde el handler y hacer el trabajo pesado (el dump a JSON) en el loop principal —
  que es exactamente el patrón que sí se siguió para SIGUSR2.

- **Clase 6/10 (Scheduling)**: la vista Scheduling combina `nice`/`priority` (campos 18-19 de
  `/proc/<pid>/stat`), la política (`SCHED_OTHER`/`FIFO`/`RR`/etc., campo 41), la `rt_priority`
  (campo 40, relevante solo para políticas de tiempo real como FIFO/RR), la afinidad de CPU
  (`Cpus_allowed_list` de `status`) y los context switches voluntarios/involuntarios. Un
  proceso CPU-bound tiende a agotar su quantum y ser desalojado por el scheduler —eso cuenta
  como *context switch involuntario*—, mientras que un proceso I/O-bound cede la CPU
  voluntariamente al bloquearse esperando I/O — *context switch voluntario*. Esta distinción
  se puede observar comparando, por ejemplo, `chrome` (con mucha actividad de red/IPC, más
  voluntarios) contra un proceso que hace cómputo puro.

- **Clases 8 y 9 (Multiprocessing fundamentos y avanzado)**: es el corazón de la arquitectura.
  Se usan `Process` para cada analizador, `Queue` para distribuir trabajo del recolector,
  `Manager().dict()` para el snapshot compartido de estructuras complejas, y `Value` (con
  `get_lock()`) tanto para los intervalos de refresco como para el flag de modo verbose —
  exactamente la distinción que se vio en clase 9 entre "`Value`/`Array` para datos simples y
  rápidos" vs. "`Manager` para estructuras Python complejas y flexibles".

- **Clase 10 (Threading / GIL)**: deliberadamente **no se usaron threads** para la arquitectura
  principal, tal como pide la consigna. La TUI usa `stdscr.nodelay(True)` para hacer polling
  no bloqueante del teclado dentro de un único proceso, en vez de un thread aparte para la
  entrada — la consigna permitía usar un thread para esto, pero no era necesario dado que
  `curses` ya ofrece un modo no bloqueante nativo. La vista Threads en sí lista los LWPs
  (`/proc/<pid>/task/<tid>/`) de cada proceso, que es como el kernel de Linux representa a los
  threads de un proceso multi-hilo (a diferencia del PID del proceso, cada LWP tiene su propio
  TID y su propia entrada en `/proc/<pid>/task/`), y calcula CPU% y context switches por
  thread individual, no solo por proceso — esto deja ver, por ejemplo, cómo el GIL limita el
  paralelismo real de un proceso Python multi-hilo: aunque tenga varios threads, normalmente
  solo uno está usando CPU de forma efectiva en un momento dado.

---

## 5. Cómo correr y testear

### Requisitos

- Docker y Docker Compose (probado con Docker 29.1.3 / Compose 2.40.3)
- Linux como sistema operativo del host o de la VM que corre Docker (el proyecto lee `/proc`,
  que no existe en macOS/Windows fuera de una VM Linux)

### Levantar el monitor

```bash
docker compose run --rm monitor
```

### Probar las señales del monitor

Necesitás el PID del proceso `main.py` **dentro** del contenedor. En otra terminal:

```bash
docker compose exec monitor sh -c "ps aux | grep main.py"
docker compose exec monitor kill -USR1 <PID>   # genera dump_estado.json
docker compose exec monitor kill -HUP <PID>    # recarga config.json en caliente
docker compose exec monitor kill -USR2 <PID>   # toggle de modo verbose
docker compose exec monitor kill -TERM <PID>   # shutdown limpio (igual a Ctrl+C)
```

El archivo `dump_estado.json` se genera en el directorio del proyecto (queda visible en el
host gracias al volumen montado en `docker-compose.yml`).

### Probar la recarga de configuración (SIGHUP)

1. Con el monitor corriendo, andá a la vista `2` (Memoria) y fijate el intervalo mostrado
   arriba a la derecha (`Refresco: 3.0s`).
2. Editá `config.json` y cambiá `"intervalo_memoria": 3.0` por otro valor, por ejemplo `8.0`.
3. Desde otra terminal, mandá `kill -HUP <PID>`.
4. El número de "Refresco" en pantalla debería cambiar sin reiniciar el monitor.

### Probar el modo verbose (SIGUSR2)

1. Con el monitor corriendo, andá a la vista `3` (FDs) y anotá cuántos FDs tiene algún proceso
   (ej. `chrome`).
2. Desde otra terminal, mandá `kill -USR2 <PID>`.
3. `VERBOSE` debería aparecer en la barra de estado, y la columna Detalle de esa fila debería
   mostrar el tipo de los primeros FDs individuales, no solo el total.
4. Mandá `kill -USR2 <PID>` de nuevo para volver al modo normal.

---

## 6. Limitaciones conocidas

- **No se incluye `requirements.txt`.** La consigna lo lista en la estructura sugerida del
  repo, pero el proyecto no tiene ninguna dependencia externa (`curses`, `multiprocessing`,
  `signal`, `os`, `time`, `json`, `pwd` son todas stdlib de Python 3.11+), así que se omitió
  deliberadamente en vez de agregar un archivo vacío sin uso real.

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

- **SIGWINCH no está implementado como handler explícito.** `SIGWINCH` ("WINdow CHange") es la
  señal que el kernel manda a los procesos con terminal controladora cuando el usuario
  redimensiona la ventana; la consigna la marca como opcional/recomendada, no obligatoria, y
  sugiere usarla para forzar un repintado. No se agregó un `signal.signal(SIGWINCH, ...)`
  porque `tui.py` ya recalcula `stdscr.getmaxyx()` en cada vuelta del loop principal (cada
  ~0.1s), así que un resize se refleja solo, sin necesidad de reaccionar a la señal
  explícitamente — el handler solo aportaría un repintado inmediato en vez de esperar hasta
  la próxima vuelta del loop (a lo sumo ~100ms de diferencia).

- **El recolector tiene un intervalo fijo de 2 segundos**, sin adaptarse dinámicamente al
  intervalo mínimo configurado en las vistas activas (ver detalle en la sección de decisiones
  de diseño, punto sobre `Queue`).

- **`leer_segmentos()` en `memoria.py` es una heurística simplificada**, no un parser completo
  de `/proc/<pid>/maps` como el de `pmap`/`smaps`: agrupa cada región por sus permisos y por si
  el path contiene `[heap]`/`[stack]`, sin desambiguar casos límite como mapeos anónimos de
  solo-lectura sin backing file, ni sumar por separado memoria compartida entre procesos
  (`shared` vs `private`) con la precisión de `/proc/<pid>/smaps`.

- **Sin sincronización explícita entre el recolector y los analizadores más allá de la `Queue`
  misma**: si un analizador es mucho más lento que el intervalo del recolector, la cola puede
  acumular listas de PIDs no consumidas. No se observaron problemas de memoria en pruebas
  cortas, pero no se testeó el comportamiento en ejecuciones de larga duración (horas) ni con
  cientos de procesos simultáneos en el sistema.

- **Los FDs y threads con detalle completo (`readlink` por FD, lectura de `/proc/<pid>/task/<tid>/...`
  por thread, ahora también context switches por thread) son más costosos que un simple conteo.**
  Para procesos con muchos FDs o threads, esto puede introducir latencia perceptible — mitigado
  parcialmente por tener intervalos de refresco más altos por defecto (5s para FDs, 2s para
  threads) que las vistas más livianas. El modo verbose (SIGUSR2), al mostrar más detalle,
  no agrega llamadas nuevas a `/proc` (ya se leían), solo cambia qué parte de lo ya leído se
  imprime en pantalla — así que no debería afectar el rendimiento del recolector/analizadores.

- **No se probó en sistemas con miles de procesos activos** ni se midió el uso de memoria del
  proceso `Manager` bajo esa carga.

---

## 7. Decisiones sobre la TUI

Se usó `curses` (biblioteca estándar de Python, sin dependencias externas) en lugar de `rich`.
La interfaz se organiza en una única función de render (`dibujar_interfaz` en `tui.py`) con un
loop principal que:

1. Calcula `altura`/`ancho` de la terminal al inicio de cada vuelta (necesario para que la
   navegación con flechas sepa cuántas filas entran en pantalla antes de hacer scroll).
2. Lee el flag de modo verbose (`modo_verbose.value`) en cada vuelta, para reflejar cambios de
   SIGUSR2 sin reiniciar el monitor — mismo patrón que el de los intervalos con `+`/`-`.
3. Lee una tecla de forma no bloqueante (`stdscr.nodelay(True)`).
4. Redibuja toda la pantalla según la vista activa, leyendo directamente del
   `snapshot_global` compartido (sin copiar datos a estructuras locales).
5. Duerme 0.1s antes de la siguiente vuelta, para no consumir CPU en un loop apretado
   mientras espera input.

Las 7 vistas de procesos (todas menos la vista `8`, Sistema Global) comparten una única tabla
base con columnas PID/Usuario/Nombre + una columna "Detalle" que cambia de contenido según la
vista activa **y** según el modo verbose (extraído a la función `formatear_detalle()`, separada
del loop de dibujado para no inflarlo). Esto permite que filtro, orden y pin funcionen de forma
consistente sin importar qué vista esté mirando el usuario, en vez de tener 7 tablas
completamente distintas con lógica de filtrado duplicada en cada una.

---

## 8. Lo que aprendí

Lo que más me cambió la forma de pensar en este TP fue entender que `/proc` no es una
abstracción "linda" que el kernel arma para que los programas de monitoreo la lean cómodos —
es básicamente una ventana directa a estructuras internas del kernel, con todos los formatos
poco amigables que eso implica: máscaras hexadecimales de 64 bits para señales, un `stat` que
hay que parsear con cuidado porque el nombre del comando puede contener espacios o paréntesis
(por eso el `rfind(')')` en vez de un `split()` ingenuo), y campos numerados por posición en
vez de por nombre. Antes de este TP pensaba en "leer el estado de un proceso" como una
operación simple; ahora entiendo por qué herramientas como `psutil` existen — hay mucho trabajo
de parseo tedioso y propenso a errores debajo de una llamada tan simple como `proceso.cpu_percent()`.

La otra gran revelación fue lo mecánico que es en realidad manejar concurrencia con
`multiprocessing`. Antes de arrancar pensaba en "race condition" como algo abstracto y difícil
de visualizar; acá lo viví concretamente al decidir, para cada dato compartido, quién lo
escribe y quién lo lee, y qué pasa si dos procesos intentan tocar el mismo dato al mismo
tiempo. Elegir `Manager().dict()` para el snapshot pero `Value` para los intervalos y el flag
de verbose no fue una decisión arbitraria: fue analizar, para cada dato, su forma (¿primitivo
o estructura compleja?), su frecuencia de escritura (¿constante o rara?) y su cantidad de
escritores (¿uno o varios?). Terminé el TP con la sensación de que la pregunta "¿qué mecanismo
de IPC uso acá?" tiene una respuesta bastante mecánica una vez que uno hace ese análisis, en
vez de sentirse como una elección arbitraria entre opciones intercambiables.

Por último, implementar SIGUSR2 después de haber hecho ya SIGUSR1 me hizo pensar en serio en la
diferencia entre "que la señal haga algo" y "que la señal haga algo *bien*". Mi primer instinto
para el toggle de verbose fue replicar el patrón de SIGUSR1 (hacer el trabajo directamente
dentro del handler), pero ahí no había ningún trabajo pesado que hacer — solo invertir un
booleano — así que terminó siendo el ejemplo más limpio del TP de lo que se supone que es un
handler de señal: tocar lo mínimo posible y dejar que el loop principal decida qué hacer con
ese cambio de estado. Irónicamente, entendí mejor el patrón *self-pipe* explicando por qué
SIGUSR1 *no* lo sigue del todo que leyéndolo en el apunte de la clase.