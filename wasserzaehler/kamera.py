"""Bilder von der ESP32-CAM (AI-on-the-edge) holen.

/capture_with_flashlight liefert ein frisches Bild mit LED, mit den Kamera- und
Zoom-Einstellungen aus der config.ini des ESP32 – aber noch ungedreht. Gedreht
wird hier genauso wie in der Firmware (InitialRotate), damit die Lesebereiche
aus der ESP32-Konfiguration 1:1 passen.
"""

import logging
import math
import time
import urllib.request

import cv2
import numpy as np

log = logging.getLogger(__name__)


def drehen_wie_firmware(bild: np.ndarray, winkel: float) -> np.ndarray:
    """Nachbau von CRotateImage::Rotate: Drehpunkt Bildmitte, gleiche Größe, weißer Rand."""
    h, b = bild.shape[:2]
    a = math.radians(winkel)
    cx, cy = b // 2, h // 2
    c, s = math.cos(a), math.sin(a)
    # Firmware rechnet Ziel → Quelle, daher WARP_INVERSE_MAP
    M = np.float32([[c, s, (1 - c) * cx - s * cy],
                    [-s, c, s * cx + (1 - c) * cy]])
    return cv2.warpAffine(bild, M, (b, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


class Kamera:
    def __init__(self, cfg: dict):
        self.host = cfg.get("host", "192.168.0.13")
        self.drehung = float(cfg.get("drehung_grad", 0.0))
        self.pause_s = float(cfg.get("pause_zwischen_fotos_s", 1.0))
        self.versuche = int(cfg.get("versuche", 4))

    def roh(self) -> bytes:
        """Ein JPEG direkt von der Kamera. Der ESP32 ist ab und zu mit seinem eigenen Durchlauf beschäftigt."""
        fehler = None
        for i in range(self.versuche):
            try:
                with urllib.request.urlopen(f"http://{self.host}/capture_with_flashlight", timeout=25) as r:
                    daten = r.read()
                if daten[:2] == b"\xff\xd8":
                    return daten
                fehler = f"kein JPEG ({len(daten)} Bytes)"
            except Exception as e:
                fehler = e
            time.sleep(3 + 3 * i)
        raise RuntimeError(f"Kamera {self.host} nicht erreichbar: {fehler}")

    @staticmethod
    def dekodieren(jpeg: bytes) -> np.ndarray:
        bild = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if bild is None:
            raise ValueError("JPEG nicht lesbar")
        return cv2.cvtColor(bild, cv2.COLOR_BGR2RGB)

    def vorbereiten(self, jpeg: bytes) -> np.ndarray:
        bild = self.dekodieren(jpeg)
        return drehen_wie_firmware(bild, self.drehung) if self.drehung else bild

    def fotos(self, anzahl: int) -> list[tuple[bytes, np.ndarray]]:
        """(Original-JPEG fürs Archiv, gedrehtes RGB-Bild) je Foto."""
        aus = []
        for i in range(anzahl):
            if i:
                time.sleep(self.pause_s)
            j = self.roh()
            aus.append((j, self.vorbereiten(j)))
        return aus
