# 🤖 PompIA – Sistema de Asistente Virtual Inteligente

**PompIA** es un sistema modular de asistente virtual construido con **Rasa** y **Python**, que permite la gestión, entrenamiento y ejecución de un bot conversacional inteligente. Está diseñado para ser escalable, mantenible y fácilmente desplegable mediante contenedores Docker.

> 💡 Este repositorio central (`pomp.ia`) organiza y orquesta los distintos módulos (bot y actions), cada uno ejecutado en su propio contenedor.

---

## 🧱 Estructura del Proyecto

```
pomp.ia/
│
│
├── bot/                # Proyecto principal del chatbot
│   ├── data/           # NLU y ejemplos de conversación
│   ├── models/         # Modelos entrenados por Rasa
│   ├── entrenador/     # Lógica de entrenamiento (opcional)
│   ├── config.yml      # Configuración del pipeline de Rasa
│   ├── domain.yml      # Intents, entidades, acciones, respuestas
│   ├── endpoints.yml   # Configuración de endpoints
│   ├── pyproject.toml  # Dependencias con Poetry
│   └── poetry.lock
│
├── actions/            # Acciones personalizadas (custom actions)
│   ├── actions.py      # Acciones en Python
│   ├── pyproject.toml
│   └── poetry.lock
│
├── docker-compose.yml  # Orquestación de servicios
├── Dockerfile.rasa     # Imagen del servicio del bot
├── Dockerfile.actions  # Imagen del servicio de acciones
├── .dockerignore       # Archivos ignorados en el build
└── README.md           # Este archivo ✨
```

---

## 🚀 ¿Qué hace este proyecto?

- 🧠 Usa **Rasa** para NLP/NLU: interpreta intenciones, entidades y contexto.
- 🎯 Implementa **acciones personalizadas** para integrar lógica adicional en Python.
- 🐳 Usa **Docker** para aislar los entornos de ejecución (bot y actions).
- 🔁 Es **modular**, cada componente es autocontenible y fácil de mantener.
- 🛠️ Puede entrenarse, probarse, actualizarse y desplegarse con un solo comando.

---

## ⚙️ Requisitos Previos

- Docker + Docker Compose
- Python 3.10+ (solo si corrés fuera de Docker)
- [Poetry](https://python-poetry.org/) (opcional si desarrollás localmente)

---

## 🧪 Cómo usarlo

### 📦 1. Build del sistema

```bash
make build
```

### ▶️ 2. Levantar el sistema

```bash
make up
```

Esto inicia los contenedores:
- `bot`: el servidor Rasa principal
- `actions`: servidor de acciones personalizadas

Podés acceder a la interfaz de Rasa en `http://localhost:5005`.

---

### 🧼 3. Mantenimiento del entorno

```bash
make clean        # Baja y elimina contenedores del proyecto actual
make prune        # Limpia TODO lo que Docker no está usando (cuidado)
make clean-all    # Limpieza más específica
make reset        # Borra todo, reconstruye y reinicia
```

---

### 🧠 4. Entrenar el modelo

```bash
make shell        # Entra al contenedor del bot
rasa train        # Entrenamiento manual
```

---

## 📦 Instalación de dependencias

Si querés trabajar localmente (fuera de Docker):

```bash
cd bot
poetry install

cd ../actions
poetry install
```

---

## 🧹 Limpieza de basura innecesaria (opcional)

Podés eliminar:

- Carpetas como `__pycache__`, `.keras/`, `.rasa/`, `.config/`
- Volúmenes o imágenes huérfanas con `make prune`

---

## 🧠 Agentes que quieran contribuir

Este proyecto está diseñado para facilitar la extensión. Podés:

- Añadir nuevos `intents` o `stories` en `bot/data`
- Escribir nuevas `acciones` en `actions/actions.py`
- Re-entrenar con `rasa train`
- Volver a levantar con `make up`

---

## 🧊 Buenas prácticas

- Usá `make` para todo: build, reset, limpieza.
- No edites directamente los contenedores: modificá el código y reconstruí.
- Hacé commits claros y documentá tus cambios en el changelog si hay.

---

## ✨ Autoría

Desarrollado con ❤️ por Ariel Habib y el equipo de Integhra.

---

## 🧾 Licencia

MIT License – Libre uso con atribución.
