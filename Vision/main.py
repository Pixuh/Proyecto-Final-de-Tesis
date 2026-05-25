import os
import time
from dataclasses import dataclass

import cv2
import requests


CAMERA_URL = os.getenv("CAMERA_RTSP_URL", "").strip()
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:3001").rstrip("/")
CAMERA_ID = os.getenv("CAMERA_ID", "main_camera")
LINE_POSITION = float(os.getenv("VISION_LINE_POSITION", "0.55"))
DETECTION_INTERVAL = int(os.getenv("VISION_DETECTION_INTERVAL", "5"))
MIN_CONFIDENCE = float(os.getenv("VISION_CONFIDENCE", "0.45"))


@dataclass
class Track:
  track_id: int
  x: int
  y: int
  last_seen: int
  counted: bool = False


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


def wait_for_camera_url():
  while not CAMERA_URL:
    print("CAMERA_RTSP_URL no configurada. El servicio Vision queda en espera.", flush=True)
    time.sleep(30)


def open_stream():
  while True:
    capture = cv2.VideoCapture(CAMERA_URL)
    if capture.isOpened():
      print("Stream de camara conectado.", flush=True)
      return capture
    print("No se pudo abrir la camara. Reintentando en 10 segundos.", flush=True)
    capture.release()
    time.sleep(10)


def main():
  wait_for_camera_url()

  hog = cv2.HOGDescriptor()
  hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
  tracker = CentroidTracker()
  last_positions = {}
  frame_index = 0
  capture = open_stream()

  while True:
    ok, frame = capture.read()
    if not ok:
      print("Frame no disponible. Reconectando stream.", flush=True)
      capture.release()
      time.sleep(5)
      capture = open_stream()
      continue

    frame_index += 1
    if frame_index % DETECTION_INTERVAL != 0:
      continue

    height, width = frame.shape[:2]
    line_y = int(height * LINE_POSITION)
    resized = cv2.resize(frame, (640, int(height * 640 / width)))
    scale_y = height / resized.shape[0]
    scale_x = width / resized.shape[1]

    boxes, weights = hog.detectMultiScale(resized, winStride=(8, 8), padding=(8, 8), scale=1.05)
    detections = []
    for (x, y, w, h), confidence in zip(boxes, weights):
      if float(confidence) < MIN_CONFIDENCE:
        continue
      detections.append((int(x * scale_x), int(y * scale_y), int(w * scale_x), int(h * scale_y)))

    for track in tracker.update(detections, frame_index):
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


if __name__ == "__main__":
  main()
