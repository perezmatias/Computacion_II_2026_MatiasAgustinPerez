import time

def iniciar_analizador_memoria(cola_in, snapshot_global, intervalo=3.0):
    """
    Proceso que lee PIDs de su cola, extrae la memoria física y virtual,
    y actualiza el diccionario compartido (snapshot global).
    """
    print("[MEMORIA] Analizador listo y esperando PIDs...")
    
    while True:
        # 1. Sacamos la lista de PIDs si hay trabajo en la cola
        if not cola_in.empty():
            pids = cola_in.get()
            
            # 2. Diccionario temporal para guardar la info de esta iteración
            datos_memoria = {}
            
            # 3. Procesamos cada PID
            for pid in pids:
                ruta_status = f"/proc/{pid}/status"
                
                try:
                    with open(ruta_status, 'r') as archivo:
                        lineas = archivo.readlines()
                        
                        # Variables por defecto por si el archivo no tiene estos campos
                        vm_rss = "N/A"
                        vm_size = "N/A"
                        
                        # Buscamos las líneas específicas
                        for linea in lineas:
                            if linea.startswith("VmRSS:"):
                                partes = linea.split()
                                vm_rss = f"{partes[1]} {partes[2]}"
                            elif linea.startswith("VmSize:"):
                                partes = linea.split()
                                vm_size = f"{partes[1]} {partes[2]}"
                                
                        # Guardamos los datos reales extraídos
                        datos_memoria[pid] = {"VmRSS": vm_rss, "VmSize": vm_size}
                        
                except FileNotFoundError:
                    # Capturamos silenciosamente si el proceso muere antes de leerlo
                    pass
                
            # 4. Actualizamos el pizarrón global de forma atómica
            snapshot_global['memoria'] = datos_memoria
            
        # Pausa según el intervalo pedido por la materia (3s por defecto)
        time.sleep(intervalo)