import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import cv2
import numpy as np
import requests
from flask import Flask, Response, jsonify


CAMERA_URL = os.getenv("CAMERA_RTSP_URL", "").strip()
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:3001").rstrip("/")
CAMERA_ID = os.getenv("CAMERA_ID", "main_camera")
LINE_POSITION = float(os.getenv("VISION_LINE_POSITION", "0.55"))
DETECTION_INTERVAL = int(os.getenv("VISION_DETECTION_INTERVAL", "5"))
MIN_CONFIDENCE = float(os.getenv("VISION_CONFIDENCE", "0.45"))
STREAM_WIDTH = int(os.getenv("VISION_STREAM_WIDTH", "640"))
STREAM_HEIGHT = int(os.getenv("VISION_STREAM_HEIGHT", "360"))
RTSP_TRANSPORT = os.getenv("VISION_RTSP_TRANSPORT", "udp")
DEMO_MIN_BOXES = int(os.getenv("VISION_DEMO_MIN_BOXES", "0"))
DETECTOR_NAME = os.getenv("VISION_DETECTOR", "yolo").strip().lower()
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolo11n.pt").strip()
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", str(MIN_CONFIDENCE)))
YOLO_IMAGE_SIZE = int(os.getenv("YOLO_IMAGE_SIZE", "416"))
YOLO_DEVICE = os.getenv("YOLO_DEVICE", "cpu").strip()

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
  response.headers["Access-Control-Allow-Origin"] = "*"
  response.headers["Access-Control-Allow-Headers"] = "Content-Type"
  response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
  return response


state_lock = threading.Lock()
latest_jpeg = None
latest_status = {
  "cameraId": CAMERA_ID,
  "connected": False,
  "detections": 0,
  "tracks": 0,
  "total": 0,
  "lastFrameAt": None,
  "source": "waiting",
  "detector": DETECTOR_NAME,
  "model": YOLO_MODEL if DETECTOR_NAME == "yolo" else "opencv-hog",
}
detector_status = {
  "name": DETECTOR_NAME,
  "model": YOLO_MODEL if DETECTOR_NAME == "yolo" else "opencv-hog",
}


@dataclass
class Track:
  track_id: int
  x: int
  y: int
  last_seen: int
  counted: bool = False


class FfmpegStream:
  def __init__(self, url):
    self.url = url
    self.process = None
    self.frame_size = STREAM_WIDTH * STREAM_HEIGHT * 3

  def open(self):
    self.close()
    input_options = []
    if self.url.lower().startswith("rtsp://"):
      input_options = ["-rtsp_transport", RTSP_TRANSPORT]

    command = [
      "ffmpeg",
      "-hide_banner",
      "-loglevel",
      "warning",
      *input_options,
      "-i",
      self.url,
      "-an",
      "-vf",
      f"scale={STREAM_WIDTH}:{STREAM_HEIGHT}",
      "-pix_fmt",
      "bgr24",
      "-f",
      "rawvideo",
      "pipe:1",
    ]
    self.process = subprocess.Popen(
      command,
      stdout=subprocess.PIPE,
      stderr=subprocess.DEVNULL,
      bufsize=self.frame_size * 2,
    )
    print(f"Intentando abrir stream de camara con ffmpeg: {self.source_label()}.", flush=True)

  def source_label(self):
    if self.url.lower().startswith("rtsp://"):
      return f"rtsp/{RTSP_TRANSPORT}"
    return "http/mjpeg"

  def read(self):
    if self.process is None or self.process.poll() is not None:
      return False, None

    raw_frame = self.process.stdout.read(self.frame_size)
    if len(raw_frame) != self.frame_size:
      return False, None

    frame = np.frombuffer(raw_frame, dtype=np.uint8)
    return True, frame.reshape((STREAM_HEIGHT, STREAM_WIDTH, 3))

  def close(self):
    if self.process is None:
      return
    self.process.terminate()
    try:
      self.process.wait(timeout=3)
    except subprocess.TimeoutExpired:
      self.process.kill()
    self.process = None


class CentroidTracker:
  def __init__(self, max_distance=90, max_missing=25):
    self.max_distance = max_distance
    self.max_missing = max_missing
    self.next_id = 1
    self.tracks = {}

  def update(self, detections, frame_index):
    centers = [(int(x + w / 2), int(y + h / 2)) for x, y, w, h in detections]
    assigned = set()

    for track in list(self.tracks.values()):
      best_index = None
      best_distance = None
      for index, (cx, cy) in enumerate(centers):
        if index in assigned:
          continue
        distance = ((track.x - cx) ** 2 + (track.y - cy) ** 2) ** 0.5
        if best_distance is None or distance < best_distance:
          best_index = index
          best_distance = distance

      if best_index is not None and best_distance <= self.max_distance:
        track.x, track.y = centers[best_index]
        track.last_seen = frame_index
        assigned.add(best_index)

    for index, (cx, cy) in enumerate(centers):
      if index not in assigned:
        self.tracks[self.next_id] = Track(self.next_id, cx, cy, frame_index)
        self.next_id += 1

    for track_id, track in list(self.tracks.items()):
      if frame_index - track.last_seen > self.max_missing:
        del self.tracks[track_id]

    return list(self.tracks.values())


class HogPersonDetector:
  name = "hog"
  model_name = "opencv-hog"

  def __init__(self):
    self.hog = cv2.HOGDescriptor()
    self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

  def detect(self, frame):
    boxes, weights = self.hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.05)
    detections = []
    for (x, y, w, h), confidence in zip(boxes, weights):
      if float(confidence) >= MIN_CONFIDENCE:
        detections.append((int(x), int(y), int(w), int(h)))
    return detections


class YoloPersonDetector:
  name = "yolo"

  def __init__(self):
    from ultralytics import YOLO

    self.model_name = YOLO_MODEL
    self.model = YOLO(YOLO_MODEL)
    print(
      f"Detector YOLO cargado: model={YOLO_MODEL}, conf={YOLO_CONFIDENCE}, imgsz={YOLO_IMAGE_SIZE}, device={YOLO_DEVICE or 'auto'}.",
      flush=True,
    )

  def detect(self, frame):
    kwargs = {
      "source": frame,
      "classes": [0],
      "conf": YOLO_CONFIDENCE,
      "imgsz": YOLO_IMAGE_SIZE,
      "verbose": False,
    }
    if YOLO_DEVICE:
      kwargs["device"] = YOLO_DEVICE

    results = self.model.predict(**kwargs)
    detections = []
    if not results:
      return detections

    result = results[0]
    if result.boxes is None:
      return detections

    for box in result.boxes:
      x1, y1, x2, y2 = box.xyxy[0].tolist()
      x = max(0, int(x1))
      y = max(0, int(y1))
      w = min(STREAM_WIDTH - x, int(x2 - x1))
      h = min(STREAM_HEIGHT - y, int(y2 - y1))
      if w > 0 and h > 0:
        detections.append((x, y, w, h))
    return detections


def build_detector():
  global detector_status

  if DETECTOR_NAME == "hog":
    print("Detector activo: OpenCV HOG.", flush=True)
    detector_status = {"name": "hog", "model": "opencv-hog"}
    return HogPersonDetector()

  try:
    detector = YoloPersonDetector()
    detector_status = {"name": detector.name, "model": detector.model_name}
    return detector
  except Exception as error:
    print(f"No se pudo cargar YOLO ({error}). Usando OpenCV HOG como respaldo.", flush=True)
    detector_status = {"name": "hog", "model": "opencv-hog"}
    return HogPersonDetector()


def send_event(direction, track_id):
  payload = {
    "cameraId": CAMERA_ID,
    "direction": direction,
    "quantity": 1,
    "metadata": {"source": "vision", "trackId": track_id},
  }
  try:
    response = requests.post(f"{BACKEND_URL}/counts/events", json=payload, timeout=5)
    response.raise_for_status()
    print(f"Evento enviado: {direction} track={track_id}", flush=True)
  except requests.RequestException as error:
    print(f"No se pudo enviar evento al backend: {error}", flush=True)


def demo_boxes():
  if DEMO_MIN_BOXES <= 0:
    return []
  anchors = [
    (0.18, 0.38, 0.08, 0.22),
    (0.36, 0.34, 0.07, 0.20),
    (0.55, 0.42, 0.08, 0.24),
    (0.72, 0.36, 0.07, 0.21),
    (0.82, 0.48, 0.08, 0.24),
    (0.45, 0.54, 0.08, 0.23),
    (0.62, 0.58, 0.08, 0.23),
    (0.25, 0.62, 0.08, 0.22),
  ]
  boxes = []
  for x, y, w, h in anchors[:DEMO_MIN_BOXES]:
    boxes.append((int(x * STREAM_WIDTH), int(y * STREAM_HEIGHT), int(w * STREAM_WIDTH), int(h * STREAM_HEIGHT)))
  return boxes


def annotate_frame(frame, detections, tracks):
  annotated = frame.copy()
  line_y = int(STREAM_HEIGHT * LINE_POSITION)

  cv2.line(annotated, (0, line_y), (STREAM_WIDTH, line_y), (0, 188, 255), 2)
  cv2.putText(annotated, f"Total: {len(detections)}", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
  cv2.putText(annotated, f"Camara: {CAMERA_ID}", (16, STREAM_HEIGHT - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

  for index, (x, y, w, h) in enumerate(detections, start=1):
    cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 2)
    cv2.putText(annotated, f"P{index}", (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

  for track in tracks:
    cv2.circle(annotated, (track.x, track.y), 4, (255, 255, 0), -1)
    cv2.putText(annotated, f"ID {track.track_id}", (track.x + 6, track.y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)

  return annotated


def publish_frame(frame, detections, tracks, connected=True):
  global latest_jpeg
  annotated = annotate_frame(frame, detections, tracks)
  ok, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
  if not ok:
    return

  with state_lock:
    latest_jpeg = buffer.tobytes()
    latest_status.update({
      "connected": connected,
      "detections": len(detections),
      "tracks": len(tracks),
      "total": len(detections),
      "lastFrameAt": datetime.now(timezone.utc).isoformat(),
      "source": "vision",
      "detector": detector_status.get("name", DETECTOR_NAME),
      "model": detector_status.get("model", YOLO_MODEL),
    })


def publish_placeholder(message):
  global latest_jpeg
  frame = np.zeros((STREAM_HEIGHT, STREAM_WIDTH, 3), dtype=np.uint8)
  frame[:] = (24, 31, 42)
  cv2.putText(frame, message, (28, STREAM_HEIGHT // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
  ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
  if ok:
    with state_lock:
      latest_jpeg = buffer.tobytes()
      latest_status.update({"connected": False, "source": "waiting"})


def wait_for_camera_url():
  while not CAMERA_URL:
    publish_placeholder("CAMERA_RTSP_URL no configurada")
    print("CAMERA_RTSP_URL no configurada. El servicio Vision queda en espera.", flush=True)
    time.sleep(30)


def open_stream():
  stream = FfmpegStream(CAMERA_URL)
  while True:
    stream.open()
    ok, frame = stream.read()
    if ok:
      print("Stream de camara conectado.", flush=True)
      return stream, frame
    publish_placeholder("Esperando video de camara")
    print("No se pudo leer el primer frame. Reintentando en 10 segundos.", flush=True)
    stream.close()
    time.sleep(10)


def vision_worker():
  wait_for_camera_url()

  detector = build_detector()
  tracker = CentroidTracker()
  last_positions = {}
  frame_index = 0
  last_detections = []
  last_tracks = []
  stream, pending_frame = open_stream()

  while True:
    if pending_frame is not None:
      ok, frame = True, pending_frame
      pending_frame = None
    else:
      ok, frame = stream.read()

    if not ok:
      print("Frame no disponible. Reconectando stream.", flush=True)
      stream.close()
      time.sleep(5)
      stream, pending_frame = open_stream()
      continue

    frame_index += 1
    if frame_index % DETECTION_INTERVAL == 0:
      try:
        detections = detector.detect(frame)
      except Exception as error:
        print(f"Error ejecutando detector {detector_status.get('name')}: {error}", flush=True)
        detections = last_detections

      if len(detections) < DEMO_MIN_BOXES:
        detections.extend(demo_boxes()[len(detections):])

      last_detections = detections
      last_tracks = tracker.update(detections, frame_index)
      line_y = int(STREAM_HEIGHT * LINE_POSITION)

      for track in last_tracks:
        previous_y = last_positions.get(track.track_id)
        last_positions[track.track_id] = track.y
        if previous_y is None or track.counted:
          continue
        if previous_y < line_y <= track.y:
          track.counted = True
          send_event("in", track.track_id)
        elif previous_y > line_y >= track.y:
          track.counted = True
          send_event("out", track.track_id)

    publish_frame(frame, last_detections, last_tracks)


@app.get("/status")
def status():
  with state_lock:
    return jsonify(latest_status)


@app.get("/snapshot.jpg")
def snapshot():
  with state_lock:
    image = latest_jpeg
  if image is None:
    publish_placeholder("Vision iniciando")
    with state_lock:
      image = latest_jpeg
  return Response(image, mimetype="image/jpeg")


@app.get("/video.mjpg")
def video_feed():
  def generate():
    while True:
      with state_lock:
        image = latest_jpeg
      if image is not None:
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + image + b"\r\n"
      time.sleep(0.08)

  return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
  threading.Thread(target=vision_worker, daemon=True).start()
  app.run(host="0.0.0.0", port=int(os.getenv("VISION_PORT", "5001")), threaded=True)
