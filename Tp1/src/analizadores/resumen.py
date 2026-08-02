import time
import pwd


def leer_cmdline(pid):
    """
    Lee /proc/<pid>/cmdline: los argumentos vienen separados por bytes nulos
    (\\x00) en vez de espacios, así que hay que partir por ahí y no por split().
    Si está vacío (típico de kernel threads), devolvemos "" y el caller usa
    el nombre corto como fallback.
    """
    try:
        with open(f"/proc/{pid}/cmdline", 'rb') as archivo:
            crudo = archivo.read()
            if not crudo:
                return ""
            partes = crudo.split(b'\x00')
            return " ".join(p.decode(errors='replace') for p in partes if p)
    except (FileNotFoundError, PermissionError):
        return ""


def iniciar_analizador_resumen(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs, extrae nombre, PPID, dueño (usuario) y comando
    completo desde /proc/<pid>/status y /proc/<pid>/cmdline.
    """
    print("[RESUMEN] Analizador listo y esperando PIDs...")

    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_resumen = {}

            for pid in pids:
                ruta_status = f"/proc/{pid}/status"
                try:
                    with open(ruta_status, 'r') as archivo:
                        lineas = archivo.readlines()

                        nombre = "N/A"
                        uid_num = -1
                        usuario = "N/A"
                        ppid = "N/A"

                        for linea in lineas:
                            if linea.startswith("Name:"):
                                nombre = linea.split()[1]
                            elif linea.startswith("Uid:"):
                                uid_num = int(linea.split()[1])
                            elif linea.startswith("PPid:"):
                                ppid = linea.split()[1]

                        if uid_num != -1:
                            try:
                                usuario = pwd.getpwuid(uid_num).pw_name
                            except KeyError:
                                usuario = str(uid_num)

                        comando = leer_cmdline(pid) or f"[{nombre}]"

                        datos_resumen[pid] = {
                            "nombre": nombre,
                            "usuario": usuario,
                            "ppid": ppid,
                            "comando": comando,
                        }

                except FileNotFoundError:
                    pass

            snapshot_global['resumen'] = datos_resumen

        time.sleep(intervalo_compartido.value)