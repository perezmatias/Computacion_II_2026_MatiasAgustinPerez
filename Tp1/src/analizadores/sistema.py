import time
import os

ESTADOS = {
    'R': 'Running', 'S': 'Sleeping', 'D': 'Disk Sleep', 'Z': 'Zombie',
    'T': 'Stopped', 't': 'Tracing Stop', 'X': 'Dead', 'x': 'Dead',
    'K': 'Wakekill', 'W': 'Waking', 'P': 'Parked'
}

def iniciar_analizador_sistema(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs, parsea /proc/<pid>/stat para obtener el estado
    y calcula el %CPU usando el delta de jiffies entre dos lecturas.
    """
    print("[SISTEMA] Analizador listo y esperando PIDs...")

    HZ = os.sysconf('SC_CLK_TCK')
    lecturas_previas = {}  # {pid: (jiffies_totales, timestamp)}

    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_sistema = {}
            ahora = time.time()

            for pid in pids:
                ruta_stat = f"/proc/{pid}/stat"
                try:
                    with open(ruta_stat, 'r') as archivo:
                        contenido = archivo.read()

                        pos_cierre = contenido.rfind(')')
                        if pos_cierre != -1:
                            resto = contenido[pos_cierre + 1:].strip().split()

                            estado_letra = resto[0]
                            estado_desc = ESTADOS.get(estado_letra, estado_letra)

                            utime = int(resto[11])
                            stime = int(resto[12])
                            jiffies_totales = utime + stime

                            cpu_pct = 0.0
                            if pid in lecturas_previas:
                                jiffies_prev, ts_prev = lecturas_previas[pid]
                                delta_jiffies = jiffies_totales - jiffies_prev
                                delta_tiempo = ahora - ts_prev

                                if delta_tiempo > 0:
                                    segundos_cpu = delta_jiffies / HZ
                                    cpu_pct = (segundos_cpu / delta_tiempo) * 100

                            lecturas_previas[pid] = (jiffies_totales, ahora)

                            datos_sistema[pid] = {
                                "estado": estado_desc,
                                "estado_letra": estado_letra,
                                "utime": utime,
                                "stime": stime,
                                "jiffies_totales": jiffies_totales,
                                "cpu_pct": round(cpu_pct, 1)
                            }
                except (FileNotFoundError, IndexError, ValueError):
                    lecturas_previas.pop(pid, None)

            pids_actuales = set(pids)
            for pid_viejo in list(lecturas_previas.keys()):
                if pid_viejo not in pids_actuales:
                    del lecturas_previas[pid_viejo]

            snapshot_global['sistema'] = datos_sistema

        time.sleep(intervalo_compartido.value)