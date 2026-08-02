import time
import signal

def decodificar_mascara(hex_str):
    """
    Convierte una máscara hexadecimal de 64 bits (formato /proc) en
    una lista de nombres de señales legibles.
    Ej: "0000000000000002" -> ["SIGINT"]
    """
    if not hex_str or hex_str == "N/A":
        return []

    try:
        mascara = int(hex_str, 16)
    except ValueError:
        return []

    nombres = []
    for bit in range(1, 65):
        if mascara & (1 << (bit - 1)):
            try:
                nombres.append(signal.Signals(bit).name)
            except ValueError:
                nombres.append(f"SIG{bit}")
    return nombres


def iniciar_analizador_senales(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs, parsea /proc/<pid>/status para extraer
    las máscaras de señales (incluyendo ShdPnd, pendientes a nivel de
    grupo de procesos, distintas de SigPnd que son pendientes del proceso
    puntual), las decodifica a nombres y actualiza el snapshot global.
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

                        sig_pnd = sig_shd = sig_blk = sig_ign = sig_cgt = "N/A"

                        for linea in lineas:
                            if linea.startswith("SigPnd:"):
                                sig_pnd = linea.split()[1]
                            elif linea.startswith("ShdPnd:"):
                                sig_shd = linea.split()[1]
                            elif linea.startswith("SigBlk:"):
                                sig_blk = linea.split()[1]
                            elif linea.startswith("SigIgn:"):
                                sig_ign = linea.split()[1]
                            elif linea.startswith("SigCgt:"):
                                sig_cgt = linea.split()[1]

                        datos_senales[pid] = {
                            "pendientes": sig_pnd,
                            "pendientes_grupo": sig_shd,
                            "bloqueadas": sig_blk,
                            "ignoradas": sig_ign,
                            "capturadas": sig_cgt,
                            "pendientes_nombres": decodificar_mascara(sig_pnd),
                            "pendientes_grupo_nombres": decodificar_mascara(sig_shd),
                            "bloqueadas_nombres": decodificar_mascara(sig_blk),
                            "ignoradas_nombres": decodificar_mascara(sig_ign),
                            "capturadas_nombres": decodificar_mascara(sig_cgt),
                        }

                except FileNotFoundError:
                    pass

            snapshot_global['senales'] = datos_senales

        time.sleep(intervalo_compartido.value)