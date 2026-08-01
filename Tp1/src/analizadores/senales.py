import time

def iniciar_analizador_senales(cola_in, snapshot_global, intervalo=3.0):
    """
    Proceso que lee PIDs, parsea /proc/<pid>/status para extraer
    las máscaras de señales y actualiza el snapshot global.
    """
    print("[SEÑALES] Analizador listo y esperando PIDs...")
    
    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_senales = {}
            
            for pid in pids:
                ruta_status = f"/proc/{pid}/status"
                
                try:
                    with open(ruta_status, 'r') as archivo:
                        lineas = archivo.readlines()
                        
                        sig_pnd = "N/A"
                        sig_blk = "N/A"
                        sig_ign = "N/A"
                        sig_cgt = "N/A"
                        
                        for linea in lineas:
                            if linea.startswith("SigPnd:"):
                                sig_pnd = linea.split()[1]
                            elif linea.startswith("SigBlk:"):
                                sig_blk = linea.split()[1]
                            elif linea.startswith("SigIgn:"):
                                sig_ign = linea.split()[1]
                            elif linea.startswith("SigCgt:"):
                                sig_cgt = linea.split()[1]
                                
                        datos_senales[pid] = {
                            "pendientes": sig_pnd,
                            "bloqueadas": sig_blk,
                            "ignoradas": sig_ign,
                            "capturadas": sig_cgt
                        }
                        
                except FileNotFoundError:
                    pass
                
            snapshot_global['senales'] = datos_senales
            
        time.sleep(intervalo)