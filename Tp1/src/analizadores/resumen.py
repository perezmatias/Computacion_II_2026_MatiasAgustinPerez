import time
import pwd

def iniciar_analizador_resumen(cola_in, snapshot_global, intervalo=2.0):
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
                                # La línea Uid en Linux tiene 4 números (Real, Effective, Saved, FS). 
                                # Nos quedamos con el primero (el Real UID)
                                uid_num = int(linea.split()[1])
                        
                        # TRUCO MÁGICO: Traducimos el número a texto
                        if uid_num != -1:
                            try:
                                usuario = pwd.getpwuid(uid_num).pw_name
                            except KeyError:
                                # Si por alguna razón el usuario no existe, dejamos el número
                                usuario = str(uid_num)
                                
                        datos_resumen[pid] = {
                            "nombre": nombre,
                            "usuario": usuario
                        }
                        
                except FileNotFoundError:
                    pass
                
            snapshot_global['resumen'] = datos_resumen
            
        time.sleep(intervalo)