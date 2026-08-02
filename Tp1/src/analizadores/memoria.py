import time

CAMPOS_STATUS = {
    "VmSize:": "VmSize",
    "VmRSS:": "VmRSS",
    "VmHWM:": "VmHWM",
    "VmData:": "VmData",
    "VmStk:": "VmStk",
    "VmExe:": "VmExe",
    "VmLib:": "VmLib",
    "VmSwap:": "VmSwap",
}


def leer_page_faults(pid):
    """
    /proc/<pid>/stat, campos 10-13 (minflt, cminflt, majflt, cmajflt).
    Se accede igual que en sistema.py: se descarta todo hasta el ')' que
    cierra el nombre del comando (puede tener espacios/paréntesis) y se
    indexa relativo a ese punto.
    """
    try:
        with open(f"/proc/{pid}/stat", 'r') as f:
            contenido = f.read()
            pos_cierre = contenido.rfind(')')
            resto = contenido[pos_cierre + 1:].strip().split()
            return {
                "minflt": int(resto[7]),
                "cminflt": int(resto[8]),
                "majflt": int(resto[9]),
                "cmajflt": int(resto[10]),
            }
    except (FileNotFoundError, IndexError, ValueError):
        return {}


def leer_segmentos(pid):
    """
    Agrupa /proc/<pid>/maps por tipo de segmento, sumando tamaño en KB:
    - heap: región marcada [heap]
    - stack: región marcada [stack]
    - text: mapeos ejecutables (permiso 'x'), típicamente el código
    - data: mapeos de escritura respaldados por archivo (binario/libs)
    - shared: mapeos compartidos (flag 's' en vez de 'p')
    - otros: todo lo que no cae en las categorías anteriores (ej: mapeos
      de solo lectura sin backing file, vdso, vvar, etc.)
    """
    segmentos = {"heap": 0, "stack": 0, "text": 0, "data": 0, "shared": 0, "otros": 0}
    try:
        with open(f"/proc/{pid}/maps", 'r') as f:
            for linea in f:
                partes = linea.split(maxsplit=5)
                if len(partes) < 2:
                    continue
                rango = partes[0]
                permisos = partes[1]
                ruta = partes[5].strip() if len(partes) > 5 else ""

                try:
                    inicio_hex, fin_hex = rango.split('-')
                    tam_kb = (int(fin_hex, 16) - int(inicio_hex, 16)) // 1024
                except ValueError:
                    continue

                if '[heap]' in ruta:
                    segmentos["heap"] += tam_kb
                elif '[stack]' in ruta:
                    segmentos["stack"] += tam_kb
                elif 'x' in permisos:
                    segmentos["text"] += tam_kb
                elif 's' in permisos:
                    segmentos["shared"] += tam_kb
                elif 'w' in permisos and ruta:
                    segmentos["data"] += tam_kb
                else:
                    segmentos["otros"] += tam_kb
    except (FileNotFoundError, PermissionError):
        pass
    return segmentos


def iniciar_analizador_memoria(cola_in, snapshot_global, intervalo_compartido):
    """
    Proceso que lee PIDs de su cola, extrae la memoria física y virtual
    (incluyendo desglose por VmXxx, page faults y segmentos de /proc/<pid>/maps),
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
                        info = {v: "N/A" for v in CAMPOS_STATUS.values()}

                        for linea in lineas:
                            for prefijo, clave in CAMPOS_STATUS.items():
                                if linea.startswith(prefijo):
                                    partes = linea.split()
                                    info[clave] = f"{partes[1]} {partes[2]}"
                                    break

                        info["faults"] = leer_page_faults(pid)
                        info["segmentos_kb"] = leer_segmentos(pid)

                        datos_memoria[pid] = info

                except FileNotFoundError:
                    pass

            snapshot_global['memoria'] = datos_memoria

        time.sleep(intervalo_compartido.value)