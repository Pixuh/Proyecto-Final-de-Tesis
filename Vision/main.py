import os
import subprocess
import time
from dataclasses import dataclass

import cv2
import numpy as np
import requests


CAMERA_URL = os.getenv("CAMERA_RTSP_URL", "").strip()
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:3001").rstrip("/")
CAMERA_ID = os.getenv("CAMERA_ID", "main_camera")
LINE_POSITION = float(os.getenv("VISION_LINE_POSITION", "0.55"))
DETECTION_INTERVAL = int(os.getenv("VISION_DETECTION_INTERVAL", "5"))
MIN_CONFIDENCE = float(os.getenv("VISION_CONFIDENCE", "0.45"))
STREAM_WIDTH = int(os.getenv("VISION_STREAM_WIDTH", "640"))
STREAM_HEIGHT = int(os.getenv("VISION_STREAM_HEIGHT", "360"))
RTSP_TRANSPORT = os.getenv("VISION_RTSP_TRANSPORT", "udp")


@dataclass
class Track:
  track_id: int
  x: int
  y: int
  last_seen: int
  counted: bool = False


class FfmpegRtspStream:
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
      stderr=subprocess.PIPE,
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
    frame = frame.reshape((STREAM_HEIGHT, STREAM_WIDTH, 3))
    return True, frame

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
  stream = FfmpegRtspStream(CAMERA_URL)
  while True:
    stream.open()
    ok, frame = stream.read()
    if ok:
      print("Stream de camara conectado.", flush=True)
      return stream, frame
    print("No se pudo leer el primer frame. Reintentando en 10 segundos.", flush=True)
    stream.close()
    time.sleep(10)


def main():
  wait_for_camera_url()

  hog = cv2.HOGDescriptor()
  hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
  tracker = CentroidTracker()
  last_positions = {}
  frame_index = 0
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
    if frame_index % DETECTION_INTERVAL != 0:
      continue

    height, width = frame.shape[:2]
    line_y = int(height * LINE_POSITION)

    boxes, weights = hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.05)
    detections = []
    for (x, y, w, h), confidence in zip(boxes, weights):
      if float(confidence) < MIN_CONFIDENCE:
        continue
      detections.append((int(x), int(y), int(w), int(h)))

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
