# Usamos una versión ligera de Python
FROM python:3.11-slim

# Creamos la carpeta de trabajo dentro del contenedor
WORKDIR /app

# Copiamos los requerimientos y los instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo tu código
COPY . .

# Comando para arrancar el servidor
CMD ["uvicorn", "main:app_fastapi", "--host", "0.0.0.0", "--port", "8000"]