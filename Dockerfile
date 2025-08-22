# ----------------------
# Etapa base
# ----------------------
FROM python:3.10-slim AS base

WORKDIR /app

# Evitar prompts y mejorar cacheo
ENV POETRY_VIRTUALENVS_CREATE=false \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copiamos dependencias primero para aprovechar cache
COPY pyproject.toml poetry.lock ./
RUN pip install --upgrade pip && pip install poetry


# ----------------------
# Etapa Bot (Rasa)
# ----------------------
FROM base AS rasa
RUN poetry install --only bot --no-root --without dev

# Clonamos solo la carpeta "bot"
RUN git clone --depth 1 --filter=blob:none --sparse https://github.com/Ariel-Hab/Integhra-Pomp.ia.git /app/repo \
    && cd /app/repo && git sparse-checkout set bot

WORKDIR /app/repo/bot
CMD ["poetry", "run", "rasa", "run", "--enable-api", "--cors", "*"]


# ----------------------
# Etapa Actions
# ----------------------
FROM base AS actions
RUN poetry install --only actions --no-root --without dev

# Clonamos solo la carpeta "actions"
RUN git clone --depth 1 --filter=blob:none --sparse https://github.com/Ariel-Hab/Integhra-Pomp.ia.git /app/repo \
    && cd /app/repo && git sparse-checkout set actions

WORKDIR /app/repo/actions
CMD ["poetry", "run", "rasa", "run", "actions"]
