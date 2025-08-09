# ----------------------
# Etapa base
# ----------------------
FROM python:3.10-slim AS base

WORKDIR /app

# Evitar prompts y mejorar cacheo
ENV POETRY_VIRTUALENVS_CREATE=false \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on

# Copiamos dependencias primero para aprovechar cache
COPY pyproject.toml poetry.lock ./
RUN pip install --upgrade pip && pip install poetry

# ----------------------
# Etapa Bot (Rasa)
# ----------------------
FROM base AS rasa
RUN poetry install --only bot --no-root --without dev
COPY bot /app/bot
WORKDIR /app/bot
CMD ["poetry", "run", "rasa", "run", "--enable-api", "--cors", "*"]

# ----------------------
# Etapa Actions
# ----------------------
FROM base AS actions
RUN poetry install --only actions --no-root --without dev
COPY actions /app/actions
WORKDIR /app/actions
CMD ["poetry", "run", "rasa", "run", "actions"]
