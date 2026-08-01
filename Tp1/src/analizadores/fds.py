import os
import time

def iniciar_analizador_fds(cola_in, snapshot_global, intervalo=3.0):
    """
    Proceso que lee PIDs, cuenta los File Descriptors en /proc/<pid>/fd/
    y actualiza el snapshot global.
    """
    print("[FDS] Analizador listo y esperando PIDs...")
    
    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_fds = {}
            
            for pid in pids:
                ruta_fd = f"/proc/{pid}/fd"
                
                try:
                    # Listamos la carpeta y contamos la longitud de esa lista
                    cantidad_fds = len(os.listdir(ruta_fd))
                    
                    # Guardamos el dato real
                    datos_fds[pid] = {"fds_abiertos": cantidad_fds}
                    
                except FileNotFoundError:
                    # El proceso murió
                    pass
                except PermissionError:
                    # DATO CLAVE: En Linux, si no sos superusuario (root), 
                    # el sistema te deniega el permiso para ver los FDs de otros usuarios.
                    # Simplemente lo ignoramos o le ponemos "N/A"
                    pass
                
            # Actualizamos el pizarrón global
            snapshot_global['fds'] = datos_fds
            
        time.sleep(intervalo)