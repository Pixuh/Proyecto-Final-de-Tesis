# Proyecto Tesis

Proyecto fullstack compuesto por:

- Frontend web con React + Vite
- Backend/API con Node.js + Express
- Base de datos PostgreSQL
- Aplicacion movil React Native

## Requisitos

Para ejecutar el proyecto se necesita tener instalado:

- Docker Desktop
- Docker Compose

## Variables de entorno

El proyecto incluye un archivo `.env.example` con las variables necesarias.

Para esta entrega, el proyecto puede ejecutarse sin crear un archivo `.env`, ya que `docker-compose.yml` incluye valores por defecto.

Variables disponibles:

```env
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_PORT=

BACKEND_PORT=
FRONTEND_PORT=

VITE_API_URL=
```

## Ejecucion con Docker Compose

Desde la raiz del proyecto, ejecutar:

```bash
docker compose up --build
```

Esto levantara los siguientes servicios:

- Base de datos PostgreSQL
- Backend/API
- Frontend web

## Puertos

Una vez iniciado el proyecto, se puede acceder a:

- Frontend web: http://localhost:5173
- Backend/API: http://localhost:3001
- PostgreSQL: localhost:5432

## Detener el proyecto

Para detener los contenedores, presionar:

```bash
Ctrl + C
```

Tambien se puede ejecutar:

```bash
docker compose down
```

## Aplicacion movil

La carpeta `Mobile` corresponde a la aplicacion movil desarrollada con React Native.

La app movil no se levanta mediante Docker Compose en esta entrega. Debe ejecutarse desde el entorno correspondiente de React Native y conectarse al backend/API.
