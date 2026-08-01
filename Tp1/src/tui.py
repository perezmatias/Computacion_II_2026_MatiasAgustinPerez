import curses
import time
import os

def dibujar_interfaz(stdscr, snapshot_global):
    stdscr.nodelay(True)
    stdscr.keypad(True) # <-- NUEVO: Le decimos a curses que escuche las flechas del teclado
    curses.curs_set(0)

    vista_actual = '1'
    scroll = 0          # <-- NUEVO: Variable para saber en qué línea estamos parados

    while True:
        tecla = stdscr.getch()
        if tecla == ord('q'):
            break
        elif tecla in [ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6'), ord('7')]:
            vista_actual = chr(tecla)
            scroll = 0  # Volvemos arriba de todo al cambiar de vista
        elif tecla == curses.KEY_DOWN:
            scroll += 1 # Bajamos
        elif tecla == curses.KEY_UP:
            if scroll > 0:
                scroll -= 1 # Subimos (sin pasar de cero)

        stdscr.clear()

        stdscr.addstr(0, 0, f"=== MONITOR DE PROCESOS (PID: {os.getpid()}) ===", curses.A_BOLD)
        stdscr.addstr(1, 0, "[1]Resumen [2]Memoria [3]FDs [4]Sistema [5]Threads [6]Señales [7]Sched | [q] Salir")
        stdscr.addstr(2, 0, "-" * 85)

        fila = 3 

        try:
            if vista_actual == '1':
                datos = snapshot_global.get('resumen', {})
                # Evitamos hacer scroll hacia la nada misma
                if scroll > max(0, len(datos) - 20): scroll = max(0, len(datos) - 20)
                
                stdscr.addstr(fila, 0, f"{'PID':<10} {'USUARIO':<15} {'NOMBRE DEL PROCESO':<30}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[scroll : scroll + 20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('usuario', '')[:14]:<15} {info.get('nombre', '')[:29]:<30}")
                    fila += 1

            elif vista_actual == '2':
                datos = snapshot_global.get('memoria', {})
                if scroll > max(0, len(datos) - 20): scroll = max(0, len(datos) - 20)
                
                stdscr.addstr(fila, 0, f"{'PID':<10} {'MEM FISICA (VmRSS)':<20} {'MEM VIRTUAL (VmSize)':<20}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[scroll : scroll + 20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('VmRSS', ''):<20} {info.get('VmSize', ''):<20}")
                    fila += 1

            elif vista_actual == '3':
                datos = snapshot_global.get('fds', {})
                if scroll > max(0, len(datos) - 20): scroll = max(0, len(datos) - 20)
                
                stdscr.addstr(fila, 0, f"{'PID':<10} {'ARCHIVOS ABIERTOS (FDs)':<25}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[scroll : scroll + 20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {str(info.get('fds_abiertos', 'N/A')):<25}")
                    fila += 1

            elif vista_actual == '4':
                datos = snapshot_global.get('sistema', {})
                if scroll > max(0, len(datos) - 20): scroll = max(0, len(datos) - 20)
                
                stdscr.addstr(fila, 0, f"{'PID':<10} {'ESTADO':<15} {'UTIME':<10} {'STIME':<10}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[scroll : scroll + 20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('estado', '')[:14]:<15} {str(info.get('utime', '')):<10} {str(info.get('stime', '')):<10}")
                    fila += 1

            elif vista_actual == '5':
                datos = snapshot_global.get('threads', {})
                if scroll > max(0, len(datos) - 20): scroll = max(0, len(datos) - 20)
                
                stdscr.addstr(fila, 0, f"{'PID':<10} {'CANTIDAD DE HILOS (LWPs)':<25}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[scroll : scroll + 20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {str(info.get('cantidad_hilos', 'N/A')):<25}")
                    fila += 1

            elif vista_actual == '6':
                datos = snapshot_global.get('senales', {})
                if scroll > max(0, len(datos) - 20): scroll = max(0, len(datos) - 20)
                
                stdscr.addstr(fila, 0, f"{'PID':<10} {'PENDIENTES':<18} {'BLOQUEADAS':<18}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[scroll : scroll + 20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('pendientes', '')[:17]:<18} {info.get('bloqueadas', '')[:17]:<18}")
                    fila += 1

            elif vista_actual == '7':
                datos = snapshot_global.get('scheduling', {})
                if scroll > max(0, len(datos) - 20): scroll = max(0, len(datos) - 20)
                
                stdscr.addstr(fila, 0, f"{'PID':<10} {'POLITICA':<20} {'PRIORIDAD':<15} {'NICE':<10}", curses.A_REVERSE)
                fila += 1
                for pid, info in list(datos.items())[scroll : scroll + 20]:
                    stdscr.addstr(fila, 0, f"{pid:<10} {info.get('politica', '')[:19]:<20} {str(info.get('prioridad', '')):<15} {str(info.get('nice', '')):<10}")
                    fila += 1

        except curses.error:
            pass

        stdscr.refresh()
        
        # Le bajamos un poquito el tiempo de espera para que 
        # las flechas respondan más rápido al tocarlas
        time.sleep(0.1)