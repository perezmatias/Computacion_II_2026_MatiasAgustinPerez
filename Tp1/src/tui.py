import curses
import time
import os

VISTAS_CON_PIDS = {'1', '2', '3', '4', '5', '6', '7'}  # todas menos la '8' (global)


def parsear_kb(valor_str):
    """Convierte 'VmRSS: 12345 kB' -> 12345 (int) para poder ordenar."""
    if not valor_str:
        return 0
    try:
        return int(valor_str.split()[0])
    except (ValueError, IndexError):
        return 0


def pedir_texto(stdscr, prompt):
    """Pide una línea de texto al usuario en la última fila de la pantalla."""
    altura, ancho = stdscr.getmaxyx()
    try:
        stdscr.addstr(altura - 1, 0, " " * (ancho - 1))
        stdscr.addstr(altura - 1, 0, prompt)
    except curses.error:
        pass
    stdscr.refresh()

    curses.echo()
    curses.curs_set(1)
    stdscr.nodelay(False)
    try:
        texto = stdscr.getstr(altura - 1, len(prompt), 40).decode('utf-8')
    except Exception:
        texto = ""
    curses.noecho()
    curses.curs_set(0)
    stdscr.nodelay(True)
    return texto.strip()


def obtener_pids_visibles(snapshot_global, orden, filtro_texto, filtro_usuario, pin_pid):
    """
    Calcula la lista de PIDs a mostrar, aplicando filtro y orden.
    Usa 'resumen' (nombre/usuario), 'sistema' (cpu%) y 'memoria' (RSS)
    como referencia cruzada, ya que cada dimensión vive en un dict distinto.
    """
    resumen = snapshot_global.get('resumen', {})
    sistema = snapshot_global.get('sistema', {})
    memoria = snapshot_global.get('memoria', {})

    pids = list(resumen.keys())

    if filtro_texto:
        pids = [p for p in pids if filtro_texto.lower() in resumen.get(p, {}).get('nombre', '').lower()]

    if filtro_usuario:
        pids = [p for p in pids if resumen.get(p, {}).get('usuario', '') == filtro_usuario]

    if orden == 'cpu':
        pids.sort(key=lambda p: sistema.get(p, {}).get('cpu_pct', 0.0), reverse=True)
    elif orden == 'rss':
        pids.sort(key=lambda p: parsear_kb(memoria.get(p, {}).get('VmRSS', '')), reverse=True)
    else:  # 'pid'
        pids.sort(key=lambda p: int(p) if p.isdigit() else 0)

    if pin_pid and pin_pid in pids:
        pids.remove(pin_pid)
        pids.insert(0, pin_pid)

    return pids


def dibujar_ayuda(stdscr):
    stdscr.clear()
    lineas = [
        "AYUDA - Monitor de Procesos",
        "",
        "1-8         Cambiar de vista",
        "Flechas up/down   Navegar por la lista",
        "Enter       Pin del proceso en la fila seleccionada",
        "/           Filtrar por nombre de comando",
        "u           Filtrar por usuario",
        "c           Alternar orden (PID / CPU% / RSS)",
        "+ / -       Ajustar intervalo de refresco de la vista activa",
        "q           Salir",
        "h / ?       Esta ayuda",
        "",
        "Presione cualquier tecla para volver...",
    ]
    for i, linea in enumerate(lineas):
        try:
            stdscr.addstr(i, 2, linea)
        except curses.error:
            pass
    stdscr.refresh()
    stdscr.nodelay(False)
    stdscr.getch()
    stdscr.nodelay(True)


def dibujar_interfaz(stdscr, snapshot_global, intervalos, limites_intervalo):
    stdscr.nodelay(True)
    stdscr.keypad(True)
    curses.curs_set(0)

    vista_actual = '1'
    scroll = 0
    fila_seleccionada = 0

    orden = 'pid'            # 'pid' | 'cpu' | 'rss'
    filtro_texto = ""
    filtro_usuario = ""
    pin_pid = None

    while True:
        altura, ancho = stdscr.getmaxyx()
        filas_disponibles = max(1, altura - 5)

        tecla = stdscr.getch()

        if tecla == ord('q'):
            break

        elif tecla in [ord(str(n)) for n in range(1, 9)]:
            vista_actual = chr(tecla)
            scroll = 0
            fila_seleccionada = 0

        elif tecla == curses.KEY_DOWN:
            fila_seleccionada += 1
            if fila_seleccionada >= filas_disponibles:
                fila_seleccionada = filas_disponibles - 1
                scroll += 1

        elif tecla == curses.KEY_UP:
            if fila_seleccionada > 0:
                fila_seleccionada -= 1
            elif scroll > 0:
                scroll -= 1

        elif tecla == ord('c'):
            orden = {'pid': 'cpu', 'cpu': 'rss', 'rss': 'pid'}[orden]

        elif tecla == ord('/'):
            filtro_texto = pedir_texto(stdscr, "Filtrar por nombre (vacio = quitar filtro): ")
            scroll = 0

        elif tecla == ord('u'):
            filtro_usuario = pedir_texto(stdscr, "Filtrar por usuario (vacio = quitar filtro): ")
            scroll = 0

        elif tecla in (ord('h'), ord('?')):
            dibujar_ayuda(stdscr)

        elif tecla in (ord('+'), ord('=')):
            info = limites_intervalo.get(vista_actual)
            if info:
                v = intervalos[info["clave"]]
                with v.get_lock():
                    v.value = min(info["maximo"], v.value + 0.5)

        elif tecla == ord('-'):
            info = limites_intervalo.get(vista_actual)
            if info:
                v = intervalos[info["clave"]]
                with v.get_lock():
                    v.value = max(info["minimo"], v.value - 0.5)

        elif tecla in (curses.KEY_ENTER, 10, 13):
            pids_actuales = obtener_pids_visibles(snapshot_global, orden, filtro_texto, filtro_usuario, pin_pid)
            indice_absoluto = scroll + fila_seleccionada
            if 0 <= indice_absoluto < len(pids_actuales):
                candidato = pids_actuales[indice_absoluto]
                pin_pid = None if pin_pid == candidato else candidato

        stdscr.clear()

        try:
            stdscr.addstr(0, 0, f"=== MONITOR DE PROCESOS (PID: {os.getpid()}) ===", curses.A_BOLD)
            stdscr.addstr(1, 0, "[1]Res [2]Mem [3]FDs [4]Sis [5]Thr [6]Sig [7]Sch [8]Glob | [h]Ayuda [q]Salir")

            info_vista = limites_intervalo.get(vista_actual)
            estado_linea = f"Orden: {orden}"
            if filtro_texto:
                estado_linea += f" | Filtro nombre: '{filtro_texto}'"
            if filtro_usuario:
                estado_linea += f" | Filtro usuario: '{filtro_usuario}'"
            if pin_pid:
                estado_linea += f" | Pin: PID {pin_pid}"
            if info_vista:
                intervalo_actual = intervalos[info_vista["clave"]].value
                estado_linea += f" | Refresco: {intervalo_actual:.1f}s (+/-)"
            stdscr.addstr(2, 0, estado_linea[:max(0, ancho - 1)])
            stdscr.addstr(3, 0, "-" * min(90, max(0, ancho - 1)))
        except curses.error:
            pass

        fila_base = 4

        try:
            if vista_actual == '8':
                datos = snapshot_global.get('sistema_global', {})
                cpu = datos.get('cpu_pct', {})
                load = datos.get('loadavg', {})
                mem = datos.get('memoria', {})

                f = fila_base
                stdscr.addstr(f, 0, "CPU (%):", curses.A_BOLD); f += 1
                stdscr.addstr(f, 2, f"user: {cpu.get('user', 0)}  system: {cpu.get('system', 0)}  idle: {cpu.get('idle', 0)}  iowait: {cpu.get('iowait', 0)}")
                f += 2
                stdscr.addstr(f, 0, "Load average:", curses.A_BOLD); f += 1
                stdscr.addstr(f, 2, f"1min: {load.get('load_1min','')}  5min: {load.get('load_5min','')}  15min: {load.get('load_15min','')}")
                f += 2
                stdscr.addstr(f, 0, "Memoria (KB):", curses.A_BOLD); f += 1
                stdscr.addstr(f, 2, f"Total: {mem.get('mem_total_kb','')}  Libre: {mem.get('mem_libre_kb','')}  Disponible: {mem.get('mem_disponible_kb','')}")
                f += 1
                stdscr.addstr(f, 2, f"Cache: {mem.get('cache_kb','')}  Swap total: {mem.get('swap_total_kb','')}  Swap libre: {mem.get('swap_libre_kb','')}")
                f += 2
                stdscr.addstr(f, 0, "Procesos:", curses.A_BOLD); f += 1
                stdscr.addstr(f, 2, f"Total: {datos.get('total_procesos','')}  Threads: {datos.get('total_threads','')}  Zombies: {datos.get('zombies','')}")
                f += 1
                stdscr.addstr(f, 2, f"Por estado: {datos.get('procesos_por_estado', {})}")
                f += 2
                stdscr.addstr(f, 0, f"Uptime: {datos.get('uptime_seg','')}s   Boot time: {datos.get('boot_time','')}")

            elif vista_actual in VISTAS_CON_PIDS:
                pids_visibles = obtener_pids_visibles(snapshot_global, orden, filtro_texto, filtro_usuario, pin_pid)
                if scroll > max(0, len(pids_visibles) - filas_disponibles):
                    scroll = max(0, len(pids_visibles) - filas_disponibles)
                pagina = pids_visibles[scroll: scroll + filas_disponibles]

                resumen = snapshot_global.get('resumen', {})
                clave_vista = {
                    '1': 'resumen', '2': 'memoria', '3': 'fds',
                    '4': 'sistema', '5': 'threads', '6': 'senales', '7': 'scheduling'
                }[vista_actual]
                datos_vista = snapshot_global.get(clave_vista, {})

                stdscr.addstr(fila_base, 0, f"{'PID':<8} {'USUARIO':<12} {'NOMBRE':<20} {'DETALLE'}", curses.A_REVERSE)
                f = fila_base + 1

                for idx, pid in enumerate(pagina):
                    info_resumen = resumen.get(pid, {})
                    info_vista_pid = datos_vista.get(pid, {})

                    if vista_actual == '1':
                        detalle = ""
                    elif vista_actual == '2':
                        detalle = f"RSS: {info_vista_pid.get('VmRSS','')}  Size: {info_vista_pid.get('VmSize','')}"
                    elif vista_actual == '3':
                        detalle = f"FDs: {info_vista_pid.get('fds_abiertos','')}"
                    elif vista_actual == '4':
                        detalle = f"Estado: {info_vista_pid.get('estado','')}  CPU%: {info_vista_pid.get('cpu_pct',0)}"
                    elif vista_actual == '5':
                        detalle = f"Hilos: {info_vista_pid.get('cantidad_hilos','')}"
                    elif vista_actual == '6':
                        blk = ",".join(info_vista_pid.get('bloqueadas_nombres', []))
                        detalle = f"Bloqueadas: {blk[:30]}"
                    elif vista_actual == '7':
                        detalle = f"{info_vista_pid.get('politica','')} nice={info_vista_pid.get('nice','')}"
                    else:
                        detalle = ""

                    marca = ">" if pid == pin_pid else " "
                    es_seleccionada = idx == fila_seleccionada
                    resaltado = curses.A_REVERSE if es_seleccionada else 0

                    linea = f"{marca}{pid:<7} {info_resumen.get('usuario','')[:11]:<12} {info_resumen.get('nombre','')[:19]:<20} {detalle}"
                    stdscr.addstr(f, 0, linea[:max(0, ancho - 1)], resaltado)
                    f += 1

        except curses.error:
            pass

        stdscr.refresh()
        time.sleep(0.1)