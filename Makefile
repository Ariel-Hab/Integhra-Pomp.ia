# Makefile

.PHONY: up down build restart logs shell clean clean-all prune reset

up:
	docker compose up

down:
	docker compose down

build:
	docker compose build

restart:
	docker compose down && docker compose up --build

logs:
	docker compose logs -f

shell:
	docker compose exec rasa bash

# 🔽 Limpieza

# Limpia solo contenedores, redes y caché del proyecto actual
clean:
	docker compose down --volumes --remove-orphans

# Elimina todo lo no usado globalmente (cuidado)
prune:
	docker system prune -af --volumes

# Limpieza total: contenedores, imágenes sin usar, redes, volúmenes
clean-all:
	docker container prune -f
	docker image prune -af
	docker volume prune -f
	docker network prune -f

# Resetea el proyecto: baja, borra y vuelve a levantar
reset:
	make clean
	make build
	make up
