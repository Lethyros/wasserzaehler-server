"""Zeiger ohne KI lesen: roten Zeiger freistellen, Spitze suchen, Winkel → Wert.

Die Diehl-Zeiger sind ein roter Tropfen: dicker runder Kopf auf der Achse und eine
dünne Spitze. Das KI-Modell hat den Kopf früher gern für die Spitze gehalten
(180° daneben). Hier zählt nur, welche roten Pixel am weitesten von der Achse weg
liegen – das ist immer die Spitze. Die Achse ist die Mitte des Lesebereichs, die
Lesebereiche sitzen nach der Ausrichtung mittig auf den Zifferblättern.
"""

import math

import cv2
import numpy as np

from .erkennung import Lesung


def rot_maske(ausschnitt_rgb: np.ndarray) -> np.ndarray:
    """Rot über den a*-Kanal (Lab): Zeiger deutlich rot, Zifferblatt leicht grünlich, Ziffern grau.

    Der Farbton allein reicht nicht – der Zeiger ist eher rotbraun und liegt je nach
    Belichtung mal bei 8, mal bei 15 (OpenCV-Skala). Auch a* wandert mit Weißabgleich
    und Belichtung (Hintergrund 115…127, Zeiger 144…163), deshalb Schwelle relativ:
    halber Weg vom Hintergrund zum rötesten Teil. Nicht glätten – die dünne Spitze
    vom x0.1-Zeiger ist teils nur 2 px breit.
    """
    a = cv2.cvtColor(ausschnitt_rgb, cv2.COLOR_RGB2LAB)[..., 1].astype(np.float32)
    hg, rot = np.median(a), np.percentile(a, 99)
    if rot - hg < 12:  # kein deutlich roter Zeiger im Bild
        return np.zeros(a.shape, np.uint8)
    return (a > hg + 0.45 * (rot - hg)).astype(np.uint8)


def lies_zeiger(ausschnitt_rgb: np.ndarray, name="") -> Lesung:
    h, b = ausschnitt_rgb.shape[:2]
    cx, cy, r = (b - 1) / 2, (h - 1) / 2, min(b, h) / 2
    m = rot_maske(ausschnitt_rgb)
    yy, xx = np.mgrid[0:h, 0:b]
    m[np.hypot(xx - cx, yy - cy) > 0.85 * r] = 0  # Ziffernkranz und Nachbarzeiger weg

    # nur das rote Teil, das die Achse berührt (Spiegelungen/Ziffern fallen raus)
    anz, etiketten, stat, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if anz < 2:
        return Lesung(name, None, 0.0)
    mitte = etiketten[int(cy) - 3:int(cy) + 4, int(cx) - 3:int(cx) + 4].ravel()
    mitte = mitte[mitte > 0]
    teil = np.bincount(mitte).argmax() if len(mitte) else 1 + int(np.argmax(stat[1:, cv2.CC_STAT_AREA]))
    zeiger = (etiketten == teil).astype(np.uint8)
    ys, xs = np.nonzero(zeiger)
    if len(xs) < 30:
        return Lesung(name, None, 0.0)

    # Achse = Mitte vom runden Kopf (dickste Stelle des Zeigers). Die Mitte des
    # Lesebereichs liegt ein paar Pixel daneben, und das gibt je nach Stellung bis
    # zu 0.3 Einheiten Winkelfehler (Archiv 25.10.: Kette x0.01→x0.001 schwankte
    # von -3.1 bis +0.6, mit der Kopfmitte nur noch -1.9 bis -0.1).
    dist = cv2.distanceTransform(zeiger, cv2.DIST_L2, 5)
    ky, kx = np.unravel_index(np.argmax(dist), dist.shape)
    if math.hypot(kx - cx, ky - cy) < 0.25 * r:
        cx, cy = float(kx), float(ky)

    dx, dy = xs - cx, ys - cy
    d = np.hypot(dx, dy)
    # nur die äußerste Spitze; ein fester Anteil der Pixel würde bei nicht ganz
    # mittiger Achse auch den Rand vom Kopf auf der Gegenseite erwischen
    weit = d >= 0.8 * d.max()
    # Richtung der Spitze, gewichtet nach Abstand
    vx, vy = (dx[weit] * d[weit]).sum(), (dy[weit] * d[weit]).sum()
    winkel = math.degrees(math.atan2(vx, -vy)) % 360  # 0° = oben, im Uhrzeigersinn
    wert = winkel / 36.0

    # Sicherheit: Spitze deutlich länger als der Kopf breit, und Spitzenpixel eng beieinander
    kopf = np.percentile(d, 50)
    laenge = d.max()
    streuung = math.hypot(vx, vy) / max((d[weit] ** 2).sum(), 1e-6)  # 1 = alle in dieselbe Richtung
    sicher = float(np.clip((laenge / max(kopf, 1) - 1.3) / 0.7, 0, 1) * np.clip((streuung - 0.7) / 0.25, 0, 1))
    return Lesung(name, wert % 10, sicher)
