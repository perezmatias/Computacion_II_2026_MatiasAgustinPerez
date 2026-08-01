# Usamos una versión ligera de Python 3.11
FROM python:3.11-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos todo el código fuente al contenedor
COPY . .

# Comando por defecto al levantar el contenedor
CMD ["python3", "src/main.py"]