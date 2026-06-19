FROM python:3.10-slim

# Instalamos las dependencias necesarias en el contenedor
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalamos Flask, el conector de base de datos y las librerías para códigos QR
RUN pip install --no-cache-dir flask mysqlclient qrcode pillow

COPY app.py .

EXPOSE 5000

CMD ["python", "app.py"]
