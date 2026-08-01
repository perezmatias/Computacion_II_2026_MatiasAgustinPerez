import time

# Diccionario para traducir los códigos numéricos de Linux a nombres legibles
POLITICAS = {
    '0': 'SCHED_OTHER',
    '1': 'SCHED_FIFO',
    '2': 'SCHED_RR',
    '3': 'SCHED_BATCH',
    '5': 'SCHED_IDLE',
    '6': 'SCHED_DEADLINE'
}

def iniciar_analizador_scheduling(cola_in, snapshot_global, intervalo=2.0):
    """
    Proceso que lee PIDs, extrae la prioridad y política de scheduling
    desde /proc/<pid>/stat y actualiza el snapshot global.
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
                        
                        # Buscamos el cierre del paréntesis del nombre del proceso
                        pos_cierre = contenido.rfind(')')
                        if pos_cierre != -1:
                            partes = contenido[pos_cierre + 1:].strip().split()
                            
                            # Los índices se desplazan -3 respecto a la documentación oficial 
                            # porque quitamos el PID (campo 1) y el Comm (campo 2).
                            # Priority = Campo 18 -> Índice 15
                            # Nice = Campo 19 -> Índice 16
                            # Policy = Campo 41 -> Índice 38
                            
                            if len(partes) > 38:
                                prioridad = partes[15]
                                nice = partes[16]
                                politica_num = partes[38]
                                
                                politica_str = POLITICAS.get(politica_num, f"UNKNOWN ({politica_num})")
                                
                                datos_sched[pid] = {
                                    "politica": politica_str,
                                    "prioridad": prioridad,
                                    "nice": nice
                                }
                except (FileNotFoundError, IndexError):
                    pass
                
            snapshot_global['scheduling'] = datos_sched
            
        time.sleep(intervalo)