# 1. Definimos el sistema operativo base
FROM python:3.11-slim

# 2. Creamos una carpeta llamada /app dentro del contenedor y nos movemos ahí
WORKDIR /app

# 3. Copiamos el archivo de dependencias
COPY requirements.txt .

# 4. Instalamos las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiamos todo el código fuente de tu carpeta src/
COPY src/ ./src/

# 6. Comando para encender el servidor
CMD ["python", "-m", "src.main"]