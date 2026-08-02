# Dudas — TP1

Preguntas y cosas que me quedaron sin resolver del todo durante el desarrollo.

---

## 1. `docker compose up` vs `curses`

Entendí que el problema es el multiplexado de logs de Compose rompiendo las secuencias de
escape de `curses`, y que `docker compose run --rm` lo evita porque conecta la terminal
directo. Pero no me queda claro **a qué nivel exacto** pasa esto — ¿Compose intercepta el
file descriptor de salida del contenedor y lo reescribe línea por línea siempre, incluso sin
`--no-log-prefix`? Probé ese flag y no cambió nada, así que sospecho que el problema no es
el prefijo en sí sino algo más profundo en cómo Compose maneja los streams de los contenedores
en modo `up`. Me gustaría entender el mecanismo interno con más precisión.

## 2. SIGUSR2 pendiente

No llegué a implementar el toggle de modo verbose vía SIGUSR2. Lo dejé documentado como
limitación en el README, pero es parte de las 5 señales que pide la consigna como obligatorias.

## 3. Recolector con intervalo fijo

¿Convendría que el recolector calculara dinámicamente su propio intervalo como el mínimo de
los intervalos activos de todas las vistas (o al menos de la vista actualmente visible en la
TUI)? Documenté esto como limitación, pero no sé si vale la pena la complejidad extra para
lo que pide el TP, o si es un over-engineering innecesario.

## 4. Costo de `Manager()` a escala

No medí qué tan lento se pone el sistema con muchos procesos corriendo (¿cientos? ¿miles?).
Sospecho que el cuello de botella sería el `Manager`, por el costo de IPC en cada escritura,
pero no lo comprobé con un benchmark real.

## 5. `fork` implícito

No until llamé a `multiprocessing.set_start_method()` en ningún lado, así que el proyecto
depende del default de Linux (`fork`). ¿Debería setearlo explícitamente aunque solo vaya a
correr en Linux, como buena práctica para dejar la intención clara en el código, aunque no
cambie el comportamiento?