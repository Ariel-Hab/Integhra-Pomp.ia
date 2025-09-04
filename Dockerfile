# Base Python 3.10 slim
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# System dependencies (if needed for Rasa/Poetry)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_HOME="/opt/poetry"
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN curl -sSL https://install.python-poetry.org | python3 -

# Copy your repo (you can mount instead with volumes if you want dynamic updates)
COPY . /app

# Install dependencies for bot or actions; you can override later
# RUN poetry install --only bot --without dev

# Expose ports for bot or actions (default ports)
EXPOSE 8000 5055

# Default command: override when running container
# CMD ["poetry", "run", "python", "main.py"]
