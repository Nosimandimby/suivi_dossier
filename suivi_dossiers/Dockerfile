# Image de base officielle Home Assistant (multi-architectures : amd64 / aarch64).
FROM ghcr.io/home-assistant/base-python:3.13-alpine3.24

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dépendances Python (roues musllinux disponibles pour amd64 et aarch64).
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Code de l'application et interface.
COPY app/main.py /app/main.py
COPY app/database.py /app/database.py
COPY app/seed.py /app/seed.py
COPY app/chemins.py /app/chemins.py
COPY app/static /app/static

COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8000

CMD [ "/run.sh" ]
