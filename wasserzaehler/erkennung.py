"""Ziffern und Zeiger mit den TFLite-Modellen von AI-on-the-edge lesen.

Unterstützte Modelle (erkannt an der Zahl der Ausgänge, wie in der Firmware):
  100  class100 (dig-class100 / ana-class100): Klasse k → k/10, also 0.0–9.9
   10  dig-cont (DoubleHyprid10): gleitender Wert aus Nachbarklassen
    2  ana-cont: (sin, cos) → Winkel → 0.0–9.99
Ausschnitte gehen als RGB mit Werten 0–255 (float, nicht normiert) rein,
genau wie auf dem ESP32.
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np

try:
    from ai_edge_litert.interpreter import Interpreter
except ImportError:  # aelteres Paket
    from tflite_runtime.interpreter import Interpreter


@dataclass
class Lesung:
    name: str
    wert: float | None  # 0.0 … 9.99, None = unlesbar
    sicherheit: float


class Modell:
    def __init__(self, pfad):
        self.it = Interpreter(model_path=str(pfad), num_threads=2)
        self.it.allocate_tensors()
        self.ein = self.it.get_input_details()[0]
        self.aus = self.it.get_output_details()[0]
        self.h, self.b = (int(v) for v in self.ein["shape"][1:3])
        self.ausgaenge = int(self.aus["shape"][1])
        if self.ausgaenge not in (2, 10, 100):
            raise ValueError(f"{pfad}: Modell mit {self.ausgaenge} Ausgängen wird nicht unterstützt")

    def __call__(self, ausschnitt_rgb: np.ndarray) -> np.ndarray:
        x = cv2.resize(ausschnitt_rgb, (self.b, self.h), interpolation=cv2.INTER_AREA)
        self.it.set_tensor(self.ein["index"], x.astype(np.float32)[None])
        self.it.invoke()
        return self.it.get_tensor(self.aus["index"])[0]

    def lies(self, ausschnitt, name="", mindestsicherheit=0.0) -> Lesung:
        o = self(ausschnitt)
        if self.ausgaenge == 2:
            wert = (math.atan2(float(o[0]), float(o[1])) / (2 * math.pi) + 2) % 1 * 10
            return Lesung(name, wert, float(min(1.0, math.hypot(o[0], o[1]))))
        if self.ausgaenge == 100:
            # Sicherheit = Wahrscheinlichkeit der Klasse plus direkte Nachbarn (0.1 daneben ist kein Fehler)
            p = _softmax(o) if o.min() < 0 or abs(o.sum() - 1) > 0.05 else o
            k = int(np.argmax(p))
            sicher = float(p[k] + p[(k + 1) % 100] + p[(k - 1) % 100])
            return Lesung(name, k / 10 if sicher >= mindestsicherheit else None, sicher)
        n = int(np.argmax(o))
        plus, minus = o[(n + 1) % 10], o[(n - 1) % 10]
        if plus > minus:
            wert, sicher = n + plus / (plus + o[n]), o[n] + plus
        else:
            wert, sicher = n - minus / (minus + o[n]), o[n] + minus
        return Lesung(name, float(wert) % 10 if sicher >= mindestsicherheit else None, float(sicher))


def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def ausschneiden(bild_rgb, roi):
    h, b = bild_rgb.shape[:2]
    x0, y0 = max(0, roi.x), max(0, roi.y)
    x1, y1 = min(b, roi.x + roi.b), min(h, roi.y + roi.h)
    return bild_rgb[y0:y1, x0:x1]
