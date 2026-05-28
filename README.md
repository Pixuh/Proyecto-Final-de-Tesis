# Proyecto Tesis

Sistema fullstack para conteo de personas usando camara IP, backend API, base de datos y dashboard web.

## Arquitectura actual

- Frontend web con React + Vite
- Backend/API con Node.js + Express
- Base de datos PostgreSQL
- Servicio Vision con Python + OpenCV + YOLO
- Aplicacion movil React Native en etapa inicial

## Requisitos

Para ejecutar el proyecto se necesita tener instalado:

- Docker Desktop
- Docker Compose

## Variables de entorno

El proyecto incluye un archivo `.env.example` con las variables necesarias.

Para desarrollo inicial, el proyecto puede ejecutarse sin crear un archivo `.env`, ya que `docker-compose.yml` incluye valores por defecto. El servicio Vision quedara en espera si no se configura `CAMERA_RTSP_URL`.

Variables disponibles:

```env
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_PORT=

BACKEND_PORT=
FRONTEND_PORT=

VITE_API_URL=

CAMERA_RTSP_URL=
CAMERA_ID=
BACKEND_URL=
VISION_CONFIDENCE=
VISION_LINE_POSITION=
VISION_DETECTION_INTERVAL=
VISION_DETECTOR=
YOLO_MODEL=
YOLO_CONFIDENCE=
YOLO_IMAGE_SIZE=
YOLO_DEVICE=
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
- Vision, servicio de procesamiento de camara

## Puertos

Una vez iniciado el proyecto, se puede acceder a:

- Frontend web: http://localhost:5173
- Backend/API: http://localhost:3001
- PostgreSQL: localhost:5432

## Endpoints principales

Verificar salud del backend:

```bash
GET http://localhost:3001/health
```

Resumen de conteos:

```bash
GET http://localhost:3001/counts/summary
```

Eventos recientes:

```bash
GET http://localhost:3001/counts/events
```

Registrar un evento de conteo:

```bash
POST http://localhost:3001/counts/events
```

Ejemplo de cuerpo JSON:

```json
{
  "cameraId": "camara_prueba",
  "direction": "in",
  "quantity": 1,
  "metadata": {
    "source": "manual-test"
  }
}
```

## Base de datos

El backend crea automaticamente la tabla `count_events` al iniciar.

Campos principales:

- `id`
- `camera_id`
- `direction`
- `quantity`
- `occurred_at`
- `metadata`

Conexion sugerida en DataGrip:

```text
Host: localhost
Port: 5432
Database: proyecto_tesis
User: postgres
Password: postgres
```

## Camara IP

El servicio Vision usa la variable `CAMERA_RTSP_URL` para conectarse a la camara IP.

Ejemplo de formato RTSP:

```text
rtsp://usuario:clave@IP_DE_LA_CAMARA:554/ruta
```

Mientras no exista una URL RTSP configurada, Vision se mantiene en espera y no detiene el resto del sistema.

### Camaras Yoosee con puente VLC

Algunas camaras Yoosee entregan RTSP en H.265 y pueden fallar al ser leidas directamente por ffmpeg/OpenCV dentro de Docker. En ese caso se puede usar VLC como puente local:

```powershell
Start-Process -FilePath "C:\Program Files\VideoLAN\VLC\vlc.exe" -ArgumentList @(
  "-I", "dummy",
  "rtsp://admin:admin123@IP_DE_LA_CAMARA:554/onvif1",
  "--sout", "#transcode{vcodec=MJPG,vb=2000,scale=1}:standard{access=http,mux=mpjpeg,dst=:8090/stream.mjpg}",
  "--no-sout-all",
  "--sout-keep"
) -WindowStyle Hidden
```

Luego configurar el stream consumido por Docker:

```env
CAMERA_RTSP_URL=http://host.docker.internal:8090/stream.mjpg
CAMERA_ID=garaje
```

Para verificar que VLC esta publicando el puente:

```powershell
Test-NetConnection 127.0.0.1 -Port 8090
```

El servicio Vision publica una salida visual para el dashboard:

```text
http://localhost:5001/video.mjpg
http://localhost:5001/snapshot.jpg
http://localhost:5001/status
```

Para una demostracion visual con mas cajas de deteccion se puede usar:

```env
VISION_DEMO_MIN_BOXES=6
```

Esta variable solo fuerza una cantidad minima de cajas visuales para presentacion. Para mediciones reales debe mantenerse en `0`.

### Detector recomendado para demostracion

Para la presentacion se recomienda usar YOLO, ya que detecta personas con mucha mayor estabilidad que el detector HOG clasico de OpenCV:

```env
VISION_DETECTOR=yolo
YOLO_MODEL=yolo11n.pt
YOLO_CONFIDENCE=0.25
YOLO_IMAGE_SIZE=416
YOLO_DEVICE=cpu
VISION_DETECTION_INTERVAL=3
```

Si el equipo queda lento, subir `VISION_DETECTION_INTERVAL` a `5` o bajar `YOLO_IMAGE_SIZE` a `320`. Si YOLO no logra cargar, el servicio usa OpenCV HOG como respaldo para que la aplicacion no se detenga.

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

La app movil no se levanta mediante Docker Compose en esta etapa. Debe ejecutarse desde el entorno correspondiente de React Native y conectarse al backend/API.
