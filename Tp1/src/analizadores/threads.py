import os
import time

ESTADOS = {
    'R': 'Running', 'S': 'Sleeping', 'D': 'Disk Sleep', 'Z': 'Zombie',
    'T': 'Stopped', 't': 'Tracing Stop', 'X': 'Dead', 'x': 'Dead',
    'K': 'Wakekill', 'W': 'Waking', 'P': 'Parked'
}


def leer_stat_thread(pid, tid):
    """Lee /proc/<pid>/task/<tid>/stat y devuelve (estado, utime, stime)."""
    with open(f"/proc/{pid}/task/{tid}/stat", 'r') as f:
        contenido = f.read()
        pos_cierre = contenido.rfind(')')
        resto = contenido[pos_cierre + 1:].strip().split()
        estado_letra = resto[0]
        utime = int(resto[11])
        stime = int(resto[12])
        return estado_letra, utime, stime


def leer_nombre_thread(pid, tid):
    try:
        with open(f"/proc/{pid}/task/{tid}/comm", 'r') as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError):
        return "?"


def leer_ctxt_switches_thread(pid, tid):
    """
    Igual que en scheduling.py pero a nivel de thread individual:
    /proc/<pid>/task/<tid>/status tiene sus propios contadores de
    context switches (independientes de los del proceso).
    """
    voluntarios = involuntarios = "N/A"
    try:
        with open(f"/proc/{pid}/task/{tid}/status", 'r') as f:
            for linea in f:
                if linea.startswith("voluntary_ctxt_switches:"):
                    voluntarios = linea.split()[1]
                elif linea.startswith("nonvoluntary_ctxt_switches:"):
                    involuntarios = linea.split()[1]
    except (FileNotFoundError, PermissionError):
        pass
    return voluntarios, involuntarios


def iniciar_analizador_threads(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs, enumera los threads (LWPs) de cada uno en
    /proc/<pid>/task/, y calcula estado + %CPU + context switches por
    thread usando delta de jiffies (mismo criterio que sistema.py, pero
    a nivel de hilo individual).
    """
    print("[THREADS] Analizador listo y esperando PIDs...")

    HZ = os.sysconf('SC_CLK_TCK')
    lecturas_previas = {}  # {(pid, tid): (jiffies_totales, timestamp)}

    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_threads = {}
            ahora = time.time()
            claves_vistas = set()

            for pid in pids:
                ruta_task = f"/proc/{pid}/task"

                try:
                    tids = os.listdir(ruta_task)
                except (FileNotFoundError, PermissionError):
                    continue

                detalle = []

                for tid in tids:
                    clave = (pid, tid)
                    claves_vistas.add(clave)

                    try:
                        estado_letra, utime, stime = leer_stat_thread(pid, tid)
                    except (FileNotFoundError, IndexError, ValueError):
                        continue

                    jiffies_totales = utime + stime
                    cpu_pct = 0.0

                    if clave in lecturas_previas:
                        jiffies_prev, ts_prev = lecturas_previas[clave]
                        delta_jiffies = jiffies_totales - jiffies_prev
                        delta_tiempo = ahora - ts_prev
                        if delta_tiempo > 0:
                            cpu_pct = (delta_jiffies / HZ / delta_tiempo) * 100

                    lecturas_previas[clave] = (jiffies_totales, ahora)

                    voluntarios, involuntarios = leer_ctxt_switches_thread(pid, tid)

                    detalle.append({
                        "tid": tid,
                        "nombre": leer_nombre_thread(pid, tid),
                        "estado": ESTADOS.get(estado_letra, estado_letra),
                        "cpu_pct": round(cpu_pct, 1),
                        "ctxt_voluntarios": voluntarios,
                        "ctxt_involuntarios": involuntarios,
                    })

                datos_threads[pid] = {
                    "cantidad_hilos": len(tids),
                    "detalle": detalle,
                }

            for clave_vieja in list(lecturas_previas.keys()):
                if clave_vieja not in claves_vistas:
                    del lecturas_previas[clave_vieja]

            snapshot_global['threads'] = datos_threads

        time.sleep(intervalo_compartido.value)