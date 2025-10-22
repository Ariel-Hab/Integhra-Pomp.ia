# Base Python 3.10 slim
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_HOME="/opt/poetry"
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN curl -sSL https://install.python-poetry.org | python3 -

# Configura Poetry para no crear un .venv dentro del proyecto
# Esto es crucial para que Docker funcione correctamente
RUN poetry config virtualenvs.create false

# Copia SÓLO los archivos de dependencias
COPY pyproject.toml poetry.lock* /app/

# Instala TODAS las dependencias (para ambos grupos, bot y actions)
# Usamos --no-root porque no necesitamos instalar el paquete "pomp-ia" en sí mismo
RUN poetry install --no-dev --no-root

# Ahora copia el resto del código de tu aplicación
COPY . /app

# Expose ports
EXPOSE 8000 5055

# El CMD será sobrescrito por docker-compose
