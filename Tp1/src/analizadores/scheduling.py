import time

POLITICAS = {
    '0': 'SCHED_OTHER',
    '1': 'SCHED_FIFO',
    '2': 'SCHED_RR',
    '3': 'SCHED_BATCH',
    '5': 'SCHED_IDLE',
    '6': 'SCHED_DEADLINE'
}


def leer_ctxt_switches(pid):
    voluntarios = involuntarios = "N/A"
    try:
        with open(f"/proc/{pid}/status", 'r') as f:
            for linea in f:
                if linea.startswith("voluntary_ctxt_switches:"):
                    voluntarios = linea.split()[1]
                elif linea.startswith("nonvoluntary_ctxt_switches:"):
                    involuntarios = linea.split()[1]
    except FileNotFoundError:
        pass
    return voluntarios, involuntarios


def leer_afinidad(pid):
    try:
        with open(f"/proc/{pid}/status", 'r') as f:
            for linea in f:
                if linea.startswith("Cpus_allowed_list:"):
                    return linea.split()[1]
    except FileNotFoundError:
        pass
    return "N/A"


def iniciar_analizador_scheduling(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs, extrae prioridad, política de scheduling, RT
    priority, afinidad de CPU, context switches y sesión/grupo de procesos
    desde /proc/<pid>/stat y /proc/<pid>/status, y actualiza el snapshot global.

    Índices de /proc/<pid>/stat usados acá (relativos a 'resto', que empieza
    en el campo 3 'state' porque se descarta todo hasta el ')' de comm):
      resto[2]  -> pgrp   (campo 5 de stat)  => PGID
      resto[3]  -> session(campo 6 de stat)  => SID
      resto[15] -> priority (campo 18)
      resto[16] -> nice     (campo 19)
      resto[37] -> rt_priority (campo 40)
      resto[38] -> policy      (campo 41)
    """
    print("[SCHEDULING] Analizador listo y esperando PIDs...")

    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_sched = {}

            for pid in pids:
                ruta_stat = f"/proc/{pid}/stat"
                try:
                    with open(ruta_stat, 'r') as archivo:
                        contenido = archivo.read()

                        pos_cierre = contenido.rfind(')')
                        if pos_cierre != -1:
                            partes = contenido[pos_cierre + 1:].strip().split()

                            if len(partes) > 38:
                                pgid = partes[2]
                                sid = partes[3]
                                prioridad = partes[15]
                                nice = partes[16]
                                rt_priority = partes[37]
                                politica_num = partes[38]

                                politica_str = POLITICAS.get(politica_num, f"UNKNOWN ({politica_num})")
                                voluntarios, involuntarios = leer_ctxt_switches(pid)

                                datos_sched[pid] = {
                                    "politica": politica_str,
                                    "prioridad": prioridad,
                                    "nice": nice,
                                    "rt_priority": rt_priority,
                                    "afinidad": leer_afinidad(pid),
                                    "ctxt_voluntarios": voluntarios,
                                    "ctxt_involuntarios": involuntarios,
                                    "pgid": pgid,
                                    "sid": sid,
                                }
                except (FileNotFoundError, IndexError):
                    pass

            snapshot_global['scheduling'] = datos_sched

        time.sleep(intervalo_compartido.value)