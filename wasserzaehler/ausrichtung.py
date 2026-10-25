"""Aktuelles Foto auf das Referenzbild ausrichten.

Statt zwei fester Marken (wie beim ESP32) werden mit ORB viele Merkmale des
Zifferblatts gesucht und daraus Drehung, Verschiebung und Maßstab berechnet.
Dadurch stimmen die Lesebereiche auch, wenn die Kamera etwas verrutscht oder
das Bild gedreht ist.
"""

import cv2
import numpy as np


class Ausrichter:
    def __init__(self, referenz_rgb: np.ndarray, arbeitsbreite: int = 800, min_treffer: int = 25):
        self.ref = referenz_rgb
        self.arbeitsbreite = arbeitsbreite
        self.min_treffer = min_treffer
        self.orb = cv2.ORB_create(nfeatures=3000)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.ref_s = arbeitsbreite / referenz_rgb.shape[1]
        self.ref_kp, self.ref_desc = self._merkmale(referenz_rgb, self.ref_s)

    def _merkmale(self, bild, s):
        grau = cv2.cvtColor(bild, cv2.COLOR_RGB2GRAY)
        grau = cv2.resize(grau, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        grau = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(grau)
        return self.orb.detectAndCompute(grau, None)

    def ausrichten(self, bild_rgb: np.ndarray) -> tuple[np.ndarray | None, dict]:
        s = self.arbeitsbreite / bild_rgb.shape[1]
        kp, desc = self._merkmale(bild_rgb, s)
        if desc is None or self.ref_desc is None:
            return None, {"fehler": "keine Merkmale gefunden"}
        paare = [m for m, n in (p for p in self.matcher.knnMatch(desc, self.ref_desc, k=2) if len(p) == 2)
                 if m.distance < 0.75 * n.distance]
        if len(paare) < self.min_treffer:
            return None, {"fehler": f"zu wenig passende Merkmale ({len(paare)})"}
        quelle = np.float32([kp[m.queryIdx].pt for m in paare]) / s
        ziel = np.float32([self.ref_kp[m.trainIdx].pt for m in paare]) / self.ref_s
        M, innen = cv2.estimateAffinePartial2D(quelle, ziel, method=cv2.RANSAC, ransacReprojThreshold=4.0 / self.ref_s)
        treffer = int(innen.sum()) if innen is not None else 0
        if M is None or treffer < self.min_treffer:
            return None, {"fehler": f"Ausrichtung unsicher ({treffer} Treffer)"}
        massstab = float(np.hypot(M[0, 0], M[1, 0]))
        winkel = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
        if not 0.7 < massstab < 1.4:
            return None, {"fehler": f"unplausibler Maßstab {massstab:.2f}"}
        h, b = self.ref.shape[:2]
        aus = cv2.warpAffine(bild_rgb, M, (b, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        self.matrix = M  # Foto → Referenz, z. B. um Bereiche im Originalfoto wiederzufinden
        return aus, {"treffer": treffer, "winkel": round(winkel, 2), "massstab": round(massstab, 3),
                     "verschiebung": [round(float(M[0, 2]), 1), round(float(M[1, 2]), 1)]}
