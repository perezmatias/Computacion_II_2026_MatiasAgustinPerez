import time

# Mapeo de la letra de estado de Linux a una descripción clara
ESTADOS = {
    'R': 'Running',
    'S': 'Sleeping',
    'D': 'Disk Sleep',
    'Z': 'Zombie',
    'T': 'Stopped',
    't': 'Tracing Stop',
    'X': 'Dead',
    'x': 'Dead',
    'K': 'Wakekill',
    'W': 'Waking',
    'P': 'Parked'
}

def iniciar_analizador_sistema(cola_in, snapshot_global, intervalo=2.0):
    """
    Proceso que lee PIDs, parsea /proc/<pid>/stat para obtener el estado
    y los ticks de CPU (utime + stime), y actualiza el snapshot global.
    """
    print("[SISTEMA] Analizador listo y esperando PIDs...")
    
    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_sistema = {}
            
            for pid in pids:
                ruta_stat = f"/proc/{pid}/stat"
                try:
                    with open(ruta_stat, 'r') as archivo:
                        contenido = archivo.read()
                        
                        # Nota técnica de robustez:
                        # El nombre del proceso va entre paréntesis y puede contener espacios.
                        # Buscamos el último ')' para asegurarnos de recortar bien los campos numéricos.
                        pos_cierre = contenido.rfind(')')
                        if pos_cierre != -1:
                            resto = contenido[pos_cierre + 1:].strip().split()
                            
                            # resto[0] -> Campo 3 (Estado)
                            # resto[11] -> Campo 14 (utime: tiempo en modo usuario)
                            # resto[12] -> Campo 15 (stime: tiempo en modo kernel)
                            estado_letra = resto[0]
                            estado_desc = ESTADOS.get(estado_letra, estado_letra)
                            
                            utime = int(resto[11])
                            stime = int(resto[12])
                            
                            datos_sistema[pid] = {
                                "estado": estado_desc,
                                "estado_letra": estado_letra,
                                "utime": utime,
                                "stime": stime,
                                "jiffies_totales": utime + stime
                            }
                except (FileNotFoundError, IndexError, ValueError):
                    pass
                
            snapshot_global['sistema'] = datos_sistema
            
        time.sleep(intervalo)