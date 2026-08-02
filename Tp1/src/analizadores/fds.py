import os
import time

def clasificar_fd(destino):
    """Clasifica el tipo de FD según el patrón de su symlink en /proc/<pid>/fd/N."""
    if destino.startswith("socket:"):
        return "socket"
    if destino.startswith("pipe:"):
        return "pipe"
    if destino.startswith("/dev/pts/") or destino == "/dev/tty":
        return "tty"
    if destino.startswith("anon_inode:"):
        return "anon_inode"
    if destino.startswith("/dev/"):
        return "device"
    return "file"


def iniciar_analizador_fds(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs, lista los File Descriptors en /proc/<pid>/fd/,
    resuelve su destino con readlink y clasifica el tipo.
    """
    print("[FDS] Analizador listo y esperando PIDs...")

    while True:
        if not cola_in.empty():
            pids = cola_in.get()
            datos_fds = {}

            for pid in pids:
                ruta_fd = f"/proc/{pid}/fd"

                try:
                    entradas = os.listdir(ruta_fd)
                    detalle = []

                    for fd_num in entradas:
                        try:
                            destino = os.readlink(f"{ruta_fd}/{fd_num}")
                            tipo = clasificar_fd(destino)
                            detalle.append({
                                "fd": fd_num,
                                "destino": destino,
                                "tipo": tipo,
                            })
                        except (FileNotFoundError, PermissionError, OSError):
                            continue

                    datos_fds[pid] = {
                        "fds_abiertos": len(entradas),
                        "detalle": detalle,
                    }

                except FileNotFoundError:
                    pass
                except PermissionError:
                    datos_fds[pid] = {"fds_abiertos": "N/A (permiso denegado)", "detalle": []}

            snapshot_global['fds'] = datos_fds

        time.sleep(intervalo_compartido.value)