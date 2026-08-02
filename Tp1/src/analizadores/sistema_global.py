import time
import os

def leer_cpu_global():
    """Lee la primera línea 'cpu ' de /proc/stat: jiffies acumulados por modo."""
    with open('/proc/stat', 'r') as f:
        for linea in f:
            if linea.startswith('cpu '):
                partes = linea.split()
                valores = list(map(int, partes[1:9]))
                return valores
    return None

def leer_loadavg():
    with open('/proc/loadavg', 'r') as f:
        partes = f.read().split()
        return {
            "load_1min": partes[0],
            "load_5min": partes[1],
            "load_15min": partes[2],
        }

def leer_meminfo():
    campos_interes = {
        "MemTotal": "mem_total_kb",
        "MemFree": "mem_libre_kb",
        "MemAvailable": "mem_disponible_kb",
        "Buffers": "buffers_kb",
        "Cached": "cache_kb",
        "SwapTotal": "swap_total_kb",
        "SwapFree": "swap_libre_kb",
    }
    resultado = {}
    with open('/proc/meminfo', 'r') as f:
        for linea in f:
            clave = linea.split(':')[0]
            if clave in campos_interes:
                valor_kb = int(linea.split()[1])
                resultado[campos_interes[clave]] = valor_kb
    return resultado

def leer_boot_uptime():
    boot_time = None
    with open('/proc/stat', 'r') as f:
        for linea in f:
            if linea.startswith('btime'):
                boot_time = int(linea.split()[1])
                break
    with open('/proc/uptime', 'r') as f:
        uptime_seg = float(f.read().split()[0])
    return boot_time, uptime_seg

def contar_procesos_por_estado():
    """Recorre /proc/*/stat contando cuántos procesos hay en cada estado."""
    conteo = {}
    total_threads = 0
    for pid_dir in os.listdir('/proc'):
        if not pid_dir.isdigit():
            continue
        try:
            with open(f"/proc/{pid_dir}/stat") as f:
                contenido = f.read()
                pos = contenido.rfind(')')
                estado = contenido[pos + 2]
                conteo[estado] = conteo.get(estado, 0) + 1
            with open(f"/proc/{pid_dir}/status") as f:
                for linea in f:
                    if linea.startswith("Threads:"):
                        total_threads += int(linea.split()[1])
                        break
        except (FileNotFoundError, IndexError):
            continue
    return conteo, total_threads


def _parsear_kb(valor_str):
    """Convierte 'VmRSS: 12345 kB' o '12345 kB' -> 12345 (int)."""
    if not valor_str or valor_str == "N/A":
        return 0
    try:
        return int(valor_str.split()[0])
    except (ValueError, IndexError):
        return 0


def calcular_top3(snapshot_global):
    """
    Deriva el top 3 por CPU% (cruzando el dict 'sistema') y el top 3 por
    RSS (cruzando el dict 'memoria'), agregando el nombre desde 'resumen'
    para que sea legible en pantalla. Esta función SOLO lee del snapshot
    (no escribe otras claves), así que no compite con los analizadores que
    escriben 'sistema'/'memoria'/'resumen' - cada uno sigue siendo dueño
    exclusivo de su propia clave.
    """
    sistema = snapshot_global.get('sistema', {})
    memoria = snapshot_global.get('memoria', {})
    resumen = snapshot_global.get('resumen', {})

    por_cpu = sorted(
        sistema.items(), key=lambda item: item[1].get('cpu_pct', 0.0), reverse=True
    )[:3]
    top_cpu = [
        {
            "pid": pid,
            "nombre": resumen.get(pid, {}).get('nombre', '?'),
            "valor": datos.get('cpu_pct', 0.0),
        }
        for pid, datos in por_cpu
    ]

    por_mem = sorted(
        memoria.items(), key=lambda item: _parsear_kb(item[1].get('VmRSS', '')), reverse=True
    )[:3]
    top_mem = [
        {
            "pid": pid,
            "nombre": resumen.get(pid, {}).get('nombre', '?'),
            "valor": _parsear_kb(datos.get('VmRSS', '')),
        }
        for pid, datos in por_mem
    ]

    return top_cpu, top_mem


def iniciar_analizador_sistema_global(snapshot_global, intervalo_compartido):
    """
    No necesita cola de PIDs: siempre mira el sistema completo, no procesos
    individuales. Por eso su firma es distinta a la de los otros analizadores.
    """
    print("[SISTEMA-GLOBAL] Analizador listo...")

    lectura_previa_cpu = None

    while True:
        cpu_actual = leer_cpu_global()
        cpu_pct = {}

        if cpu_actual and lectura_previa_cpu:
            deltas = [a - b for a, b in zip(cpu_actual, lectura_previa_cpu)]
            total_delta = sum(deltas)
            if total_delta > 0:
                nombres = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"]
                cpu_pct = {
                    nombre: round((delta / total_delta) * 100, 1)
                    for nombre, delta in zip(nombres, deltas)
                }

        lectura_previa_cpu = cpu_actual

        boot_time, uptime_seg = leer_boot_uptime()
        conteo_estados, total_threads = contar_procesos_por_estado()
        top_cpu, top_mem = calcular_top3(snapshot_global)

        datos = {
            "cpu_pct": cpu_pct,
            "loadavg": leer_loadavg(),
            "memoria": leer_meminfo(),
            "boot_time": boot_time,
            "uptime_seg": round(uptime_seg, 1),
            "procesos_por_estado": conteo_estados,
            "total_procesos": sum(conteo_estados.values()),
            "total_threads": total_threads,
            "zombies": conteo_estados.get('Z', 0),
            "top_cpu": top_cpu,
            "top_mem": top_mem,
        }

        snapshot_global['sistema_global'] = datos
        time.sleep(intervalo_compartido.value)