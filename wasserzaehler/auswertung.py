"""Einzellesungen zu einem Zählerstand zusammensetzen und auf Plausibilität prüfen.

Jede Stelle (Rolle oder Zeiger) wird mit ihrer rechten Nachbarstelle (der
niederwertigeren) abgeglichen: Steht die Nachbarstelle bei p (0–9.99), muss der
Nachkommaanteil der Stelle zwischen max(0, p-9) (Rolle springt erst am Ende
weiter, „Malteserkreuz“) und p/10 (läuft gleichmäßig mit) liegen. Gewählt wird die
ganze Zahl k, bei der das am besten passt. So kippen halb gedrehte Rollen nicht
falsch, egal wie der Zähler mechanisch gebaut ist. Eine Rolle, die ihrer rechten
Nachbarin „voraus“ wäre, ist mechanisch unmöglich und wird doppelt bestraft – das
fängt unscharfe Rollen ab, die das Modell halb auf die nächste Zahl schätzt.
"""

import math
import time
from dataclasses import dataclass, field


def _abstand(f: float, lo: float, hi: float, voraus: float) -> float:
    return voraus * (lo - f) if f < lo else f - hi if f > hi else 0.0


def stelle(wert: float, vorgaenger: float | None, rolle: bool = True) -> int:
    """Ganze Ziffer einer Stelle; vorgaenger = gleitender Wert der Stelle rechts davon.

    rolle=False für Zeiger: die laufen gleichmäßig mit, „voraus“ wird nicht extra bestraft.
    """
    if vorgaenger is None:
        return int(math.floor(wert + 1e-9)) % 10
    lo, hi = max(0.0, vorgaenger - 9.0), vorgaenger / 10.0
    basis = math.floor(wert)
    k = min((basis - 1, basis, basis + 1), key=lambda k: (_abstand(wert - k, lo, hi, 2.0 if rolle else 1.0), abs(wert - k - (lo + hi) / 2)))
    return int(k) % 10


def _als_vorgaenger(wert: float, k: int) -> float:
    """Gleitwert für die nächste Stelle links: auf [k, k+0.99] begrenzt, kein Umlauf."""
    d = wert - k
    if d > 5:
        d -= 10
    elif d < -5:
        d += 10
    return k + min(max(d, 0.0), 0.99)


def zusammensetzen(ziffern: list[float | None], zeiger: list[float],
                   letzter: float | None = None) -> tuple[float | None, str]:
    """ziffern/zeiger jeweils von der höchsten zur niedrigsten Stelle.

    Zeiger: x0.1, x0.01, … Ziffern: Rollen vor dem Komma. Unlesbare Rollen (None)
    werden aus dem letzten gültigen Stand ergänzt, sonst gibt es kein Ergebnis.
    Rückgabe: (Wert, Stellen als Text, z. B. "00401.0511"; N = unlesbar).
    """
    vorg = None
    nachkomma = []
    for w in reversed(zeiger):
        k = stelle(w, vorg, rolle=False)
        nachkomma.insert(0, k)
        vorg = _als_vorgaenger(w, k)
    vorkomma = []
    alt = None
    if letzter is not None:
        alt = str(int(letzter)).zfill(len(ziffern))[-len(ziffern):] if ziffern else ""
    for i in range(len(ziffern) - 1, -1, -1):
        w = ziffern[i]
        if w is None:
            if alt is None:
                roh = "".join("N" if z is None else str(int(z) % 10) for z in ziffern)
                return None, roh + ("." + "".join(map(str, nachkomma)) if nachkomma else "")
            k = int(alt[i])
            w = float(k)
        else:
            k = stelle(w, vorg)
        vorkomma.insert(0, k)
        vorg = _als_vorgaenger(w, k)
    roh = "".join(map(str, vorkomma)) + ("." + "".join(map(str, nachkomma)) if nachkomma else "")
    wert = int("".join(map(str, vorkomma)) or "0")
    for i, k in enumerate(nachkomma, 1):
        wert += k / 10 ** i
    return round(wert, len(nachkomma)), roh


def median(werte: list[float]) -> float:
    s = sorted(werte)
    return s[len(s) // 2]


@dataclass
class Plausibilitaet:
    """Verhindert Sprünge – hängt aber nicht ewig fest wie der ESP32.

    Weicht eine Lesung unplausibel ab, wird sie verworfen. Liefern die nächsten
    `neuabgleich_nach` Messungen untereinander einen stimmigen Stand, wird dieser
    als neuer Ausgangswert übernommen (z. B. nach Zählertausch oder falschem Startwert).
    Als Kandidat zählt nur eine Messung, bei der `neuabgleich_erlaubt` gilt (der Dienst
    verlangt klare Rollen und hohes Vertrauen) – sonst gleicht beschlagenes Glas, das
    stundenlang dieselbe falsche Zahl zeigt, den Stand auf Unsinn ab.
    """
    max_durchfluss_m3h: float = 4.0
    neuabgleich_nach: int = 6
    rueckwaerts_toleranz: float = 0.0005
    letzter: float | None = None
    letzte_zeit: float | None = None
    kandidaten: list = field(default_factory=list)

    def pruefe(self, wert: float | None, jetzt: float | None = None,
               neuabgleich_erlaubt: bool = True) -> tuple[float | None, str]:
        jetzt = time.time() if jetzt is None else jetzt
        if wert is None:
            return None, "unlesbar"
        if self.letzter is None:
            return self._uebernehmen(wert, jetzt, "erster Wert")
        diff = wert - self.letzter
        stunden = max((jetzt - (self.letzte_zeit or jetzt)) / 3600, 1 / 60)
        if -self.rueckwaerts_toleranz <= diff < 0:
            return self.letzter, "ok (Rauschen rückwärts ignoriert)"
        if 0 <= diff <= self.max_durchfluss_m3h * stunden + 0.002:
            return self._uebernehmen(wert, jetzt, "ok")
        grund = "rückwärts" if diff < 0 else f"Sprung +{diff:.4f} m³"
        if not neuabgleich_erlaubt:
            return None, f"verworfen: {grund} (zählt nicht für Neuabgleich)"
        self.kandidaten.append((wert, jetzt))
        k = self.kandidaten[-self.neuabgleich_nach:]
        if len(k) >= self.neuabgleich_nach and all(
                0 <= b[0] - a[0] <= self.max_durchfluss_m3h * max((b[1] - a[1]) / 3600, 1 / 60) + 0.002
                for a, b in zip(k, k[1:])):
            return self._uebernehmen(wert, jetzt, f"Neuabgleich ({grund}, {len(k)}× bestätigt)")
        return None, f"verworfen: {grund}"

    def _uebernehmen(self, wert, jetzt, status):
        self.letzter, self.letzte_zeit = wert, jetzt
        self.kandidaten.clear()
        return wert, status
