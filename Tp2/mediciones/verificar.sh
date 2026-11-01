#!/usr/bin/env bash
# Verificación automática de los pasos 1 a 6. Requiere la API levantada y python3.
# Uso: bash verificar.sh        (dentro de Docker el mock se llama "mock:9000")
API=${API:-http://localhost:8000}
MOCK=${MOCK:-mock:9000}
H='content-type: application/json'
ok=0; mal=0

campo()  { python3 -c "import sys,json;print(json.load(sys.stdin).get('$1'))"; }
crear()  { curl -s -X POST "$API/tareas" -H "$H" -d "$1" | campo id; }
estado() { curl -s "$API/tareas/$1" | campo estado; }
cancelar(){ curl -s -X DELETE "$API/tareas/$1" | campo estado; }
# espera hasta que la tarea termine (máx $2 segundos) y devuelve su estado final
terminal() {
  local fin=$((SECONDS + ${2:-20})) e
  while [ $SECONDS -lt $fin ]; do
    e=$(estado "$1")
    case "$e" in completada|fallida|cancelada) echo "$e"; return;; esac
    sleep 0.2
  done
  echo "$e (no terminó a tiempo)"
}
chk() {
  if [ "$2" = "$3" ]; then echo "  OK    $1"; ok=$((ok+1))
  else echo "  FALLA $1  (esperado: $3 | obtenido: $2)"; mal=$((mal+1)); fi
}

echo "== Paso 1: validación =="
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/tareas" -H "$H" -d '{"tipo":"foo"}')
chk "tipo inválido devuelve 422" "$code" "422"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/tareas" -H "$H" -d '{"tipo":"descargar"}')
chk "descargar sin urls devuelve 422" "$code" "422"

echo "== Paso 2: cancelar tareas en ejecución (5 veces) y comprobar que los workers siguen vivos =="
for i in 1 2 3 4 5; do
  id=$(crear '{"tipo":"esperar","tiempo":60,"timeout":100}'); sleep 0.3
  chk "cancelación $i de tarea en ejecución" "$(cancelar "$id")" "cancelada"
done
id=$(crear '{"tipo":"esperar","tiempo":1}')
chk "tarea normal después de 5 cancelaciones" "$(terminal "$id" 10)" "completada"

echo "== Paso 3: cancelar una tarea pendiente (3 workers ocupados, la 4ª se cancela) =="
for i in 1 2 3; do crear '{"tipo":"esperar","tiempo":4}' >/dev/null; done
id4=$(crear '{"tipo":"esperar","tiempo":1}')
chk "cancelar tarea pendiente" "$(cancelar "$id4")" "cancelada"
echo "  (esperando 6 s a que los workers se liberen y miren la cola...)"; sleep 6
chk "la cancelada NO se ejecutó (sigue cancelada)" "$(estado "$id4")" "cancelada"
chk "la cancelada nunca tuvo 'inicio'" "$(curl -s "$API/tareas/$id4" | campo inicio)" "None"

echo "== Paso 4: errores y timeout =="
id=$(crear "{\"tipo\":\"descargar\",\"urls\":[\"http://nohost.invalid/x\",\"http://$MOCK/delay/1\"]}")
chk "descargar con una URL rota termina completada" "$(terminal "$id" 20)" "completada"
r=$(curl -s "$API/tareas/$id" | python3 -c "
import sys,json;t=json.load(sys.stdin)['resultado']
print('error' if t[0]['error'] else 'sin_error', t[1]['status'])")
chk "URL rota reporta error / URL buena da 200" "$r" "error 200"
id=$(crear '{"tipo":"esperar","tiempo":5,"timeout":1}')
chk "timeout pasa la tarea a fallida" "$(terminal "$id" 10)" "fallida"
chk "el motivo menciona el timeout" "$(curl -s "$API/tareas/$id" | campo error | grep -c 'Timeout')" "1"

echo "== Paso 5: el event loop no se congela con una tarea CPU-bound =="
id=$(crear '{"tipo":"hashear","texto":"hola","iteraciones":10000000,"timeout":120}'); sleep 0.5
max=0
for i in 1 2 3 4 5 6; do
  t=$(curl -s -o /dev/null -w "%{time_total}" "$API/tareas")
  max=$(python3 -c "print(max($max,$t))"); sleep 0.2
done
echo "  latencia máxima de GET /tareas mientras hashea: ${max}s"
chk "GET /tareas responde en < 0.5 s durante el hash" "$(python3 -c "print('si' if $max<0.5 else 'no')")" "si"
chk "el hash termina completada" "$(terminal "$id" 90)" "completada"
id=$(crear '{"tipo":"hashear","texto":"x","iteraciones":900000000,"timeout":600}'); sleep 1
chk "cancelar un hashear en ejecución" "$(cancelar "$id")" "cancelada"
id=$(crear '{"tipo":"hashear","texto":"x","iteraciones":100000,"timeout":60}')
chk "después de cancelar, el pool sigue sirviendo" "$(terminal "$id" 15)" "completada"

echo "== Paso 6: filtro y estadísticas =="
r=$(curl -s "$API/tareas?estado=cancelada" | python3 -c "
import sys,json;l=json.load(sys.stdin)
print('ok' if l and all(t['estado']=='cancelada' for t in l) else 'mal')")
chk "filtro ?estado=cancelada" "$r" "ok"
r=$(curl -s "$API/estadisticas" | python3 -c "
import sys,json;e=json.load(sys.stdin)
print('ok' if all(k in e for k in ('totales_por_estado','workers_ocupados','tiempo_promedio_ejecucion_s')) else 'mal')")
chk "/estadisticas tiene totales, workers y tiempos" "$r" "ok"
curl -s "$API/estadisticas" | python3 -m json.tool

echo
echo "=============== RESUMEN: $ok OK, $mal FALLAS ==============="