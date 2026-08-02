import time

def iniciar_analizador_memoria(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs de su cola, extrae la memoria física y virtual,
    y actualiza el diccionario compartido (snapshot global).
    """
    print("[MEMORIA] Analizador listo y esperando PIDs...")

    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_memoria = {}

            for pid in pids:
                ruta_status = f"/proc/{pid}/status"

                try:
                    with open(ruta_status, 'r') as archivo:
                        lineas = archivo.readlines()

                        vm_rss = "N/A"
                        vm_size = "N/A"

                        for linea in lineas:
                            if linea.startswith("VmRSS:"):
                                partes = linea.split()
                                vm_rss = f"{partes[1]} {partes[2]}"
                            elif linea.startswith("VmSize:"):
                                partes = linea.split()
                                vm_size = f"{partes[1]} {partes[2]}"

                        datos_memoria[pid] = {"VmRSS": vm_rss, "VmSize": vm_size}

                except FileNotFoundError:
                    pass

            snapshot_global['memoria'] = datos_memoria

        time.sleep(intervalo_compartido.value)