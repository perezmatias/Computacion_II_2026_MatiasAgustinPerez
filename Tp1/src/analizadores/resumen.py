import time
import pwd

def iniciar_analizador_resumen(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs, extrae el nombre del proceso y el dueño (Usuario)
    desde /proc/<pid>/status, traduciendo el UID a nombre de texto con pwd.
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

                        for linea in lineas:
                            if linea.startswith("Name:"):
                                nombre = linea.split()[1]
                            elif linea.startswith("Uid:"):
                                uid_num = int(linea.split()[1])

                        if uid_num != -1:
                            try:
                                usuario = pwd.getpwuid(uid_num).pw_name
                            except KeyError:
                                usuario = str(uid_num)

                        datos_resumen[pid] = {
                            "nombre": nombre,
                            "usuario": usuario
                        }

                except FileNotFoundError:
                    pass

            snapshot_global['resumen'] = datos_resumen

        time.sleep(intervalo_compartido.value)