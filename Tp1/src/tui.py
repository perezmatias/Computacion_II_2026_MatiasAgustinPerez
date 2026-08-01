import curses
import time

def dibujar_interfaz(stdscr, snapshot_global):
    # Configuración básica de curses
    stdscr.nodelay(True)  # No bloquear el programa esperando que el usuario aprete una tecla
    curses.curs_set(0)    # Ocultar el cursor titilante de la terminal

    vista_actual = '1'    # Por defecto arrancamos en la vista de Resumen

    while True:
        # 1. Escuchar el teclado
        tecla = stdscr.getch()
        if tecla == ord('q'):  # Si aprieta la 'q', salimos del programa
            break
        elif tecla in [ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6'), ord('7')]:
            vista_actual = chr(tecla) # Cambiamos la vista actual

        # 2. Limpiar la pantalla para redibujar
        stdscr.clear()

        # 3. Dibujar la cabecera (Menú)
        stdscr.addstr(0, 0, "=== MONITOR DE PROCESOS (TP1) ===", curses.A_BOLD)
        stdscr.addstr(1, 0, "[1]Resumen [2]Memoria [3]FDs [4]Sistema [5]Threads [6]Señales [7]Sched | [q] Salir")
        stdscr.addstr(2, 0, "-" * 85)

        fila = 3 # A partir de la fila 3 empezamos a dibujar los datos

        # 4. Dibujar la tabla según la vista seleccionada
        try:
            if vista_actual == '1':
                datos = snapshot_global.get('resumen', {})
                stdscr.addstr(fila, 0, f"{'PID':<10} {'USUARIO':<15} {'NOMBRE DEL PROCESO':<30}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[:20]: # Mostramos máx 20 para no romper la pantalla
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('usuario', '')[:14]:<15} {info.get('nombre', '')[:29]:<30}")
                    fila += 1

            elif vista_actual == '2':
                datos = snapshot_global.get('memoria', {})
                stdscr.addstr(fila, 0, f"{'PID':<10} {'MEM FISICA (VmRSS)':<20} {'MEM VIRTUAL (VmSize)':<20}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[:20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('VmRSS', ''):<20} {info.get('VmSize', ''):<20}")
                    fila += 1

            elif vista_actual == '3':
                datos = snapshot_global.get('fds', {})
                stdscr.addstr(fila, 0, f"{'PID':<10} {'ARCHIVOS ABIERTOS (FDs)':<25}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[:20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {str(info.get('fds_abiertos', 'N/A')):<25}")
                    fila += 1

            elif vista_actual == '4':
                datos = snapshot_global.get('sistema', {})
                stdscr.addstr(fila, 0, f"{'PID':<10} {'ESTADO':<15} {'UTIME':<10} {'STIME':<10}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[:20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('estado', '')[:14]:<15} {str(info.get('utime', '')):<10} {str(info.get('stime', '')):<10}")
                    fila += 1

            elif vista_actual == '5':
                datos = snapshot_global.get('threads', {})
                stdscr.addstr(fila, 0, f"{'PID':<10} {'CANTIDAD DE HILOS (LWPs)':<25}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[:20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {str(info.get('cantidad_hilos', 'N/A')):<25}")
                    fila += 1

            elif vista_actual == '6':
                datos = snapshot_global.get('senales', {})
                stdscr.addstr(fila, 0, f"{'PID':<10} {'PENDIENTES':<18} {'BLOQUEADAS':<18}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[:20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('pendientes', '')[:17]:<18} {info.get('bloqueadas', '')[:17]:<18}")
                    fila += 1

            elif vista_actual == '7':
                datos = snapshot_global.get('scheduling', {})
                stdscr.addstr(fila, 0, f"{'PID':<10} {'POLITICA':<20} {'PRIORIDAD':<15} {'NICE':<10}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[:20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('politica', '')[:19]:<20} {str(info.get('prioridad', '')):<15} {str(info.get('nice', '')):<10}")
                    fila += 1

        except curses.error:
            # Si la terminal es muy chica y tratamos de dibujar afuera de los límites,
            # curses tira error. Lo capturamos para que no explote el programa.
            pass

        # 5. Refrescar la pantalla con los nuevos datos
        stdscr.refresh()
        
        # Dormimos un poquito para no derretir la CPU dibujando
        time.sleep(0.5)