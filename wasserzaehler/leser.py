"""Fotos → Zählerstand mit Vertrauenswert (ohne Kamera/MQTT, damit es am PC testbar ist).

Ablauf je Messung:
  1. jedes Foto auf das Referenzbild ausrichten (die Kamera wandert ein paar Pixel)
  2. Rollen mit dem Ziffernmodell, Zeiger doppelt: KI-Modell und rote Spitze (zeiger_cv)
  3. je Zeiger KI und Spitze zusammenführen; widersprechen sie sich, entscheidet,
     was besser zum Nachbarzeiger passt
  4. Stellen zu einem Wert zusammensetzen (auswertung.zusammensetzen) – je Foto
  5. Median der Fotowerte; Vertrauen 0–100 aus Einigkeit der Methoden, Kette der
     Zeiger und Einigkeit der Fotos

Beschlagenes Glas: Fließt kaltes Wasser, beschlägt das Sichtfenster oft für Stunden.
Die roten Zeiger bleiben meist lesbar, die Ziffernrollen nicht – das Modell liest dann
gern „0“. Deshalb wird der Kontrast jeder Rolle mit dem Referenzbild verglichen; ist er
zu schwach, kommen die ganzen m³ aus dem letzten Stand und nur die Zeiger werden gelesen.
"""

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .auswertung import zusammensetzen
from .ausrichtung import Ausrichter
from .erkennung import Modell, ausschneiden
from .zeiger_cv import lies_zeiger as lies_spitze


def kreis_abstand(a: float, b: float, umfang: float = 10.0) -> float:
    """Kürzester Abstand zweier Zeigerwerte auf dem Zifferblatt (9.9 und 0.1 liegen 0.2 auseinander)."""
    d = (a - b) % umfang
    return min(d, umfang - d)


def kreis_median(werte: list[float], umfang: float = 10.0) -> float:
    """Median auf dem Kreis: der Wert mit der kleinsten Summe der Abstände zu allen anderen."""
    return min(werte, key=lambda w: sum(kreis_abstand(w, x, umfang) for x in werte))


def kreis_mittel(a: float, b: float, umfang: float = 10.0) -> float:
    d = (b - a) % umfang
    if d > umfang / 2:
        d -= umfang
    return (a + d / 2) % umfang


def ketten_rest(zeiger: float, nachfolger: float) -> float:
    """Wie weit der Nachkommaanteil eines Zeigers vom Stand des nächstkleineren abweicht.

    Ergebnis mit Vorzeichen in Einheiten des Nachfolgers (-5 … 5). x0.01 auf 2.43
    erwartet x0.001 bei 4.3; steht der auf 7.35, ist der Rest -3.05. Die Zeiger sind
    mechanisch nicht exakt zueinander ausgerichtet – dieser feste Versatz wird mit
    `kalibrieren` aus dem Archiv gelernt und abgezogen (konfig: ketten_versatz).
    """
    d = ((zeiger % 1) * 10 - nachfolger) % 10
    return d - 10 if d > 5 else d


def kontrast(ausschnitt_rgb: np.ndarray) -> float:
    """Spanne der Helligkeit (5.–95. Perzentil); robust gegen einzelne Spiegelungen."""
    g = cv2.cvtColor(ausschnitt_rgb, cv2.COLOR_RGB2GRAY)
    return float(np.percentile(g, 95) - np.percentile(g, 5))


def ganze_aus_letztem(nachkomma: float, letzter: float) -> int:
    """Ganze m³ zu einem Nachkommaanteil, passend zum letzten Stand.

    Hat der x0.1-Zeiger seit dem letzten Stand die Null überschritten (0.97 → 0.02),
    ist die m³-Rolle eins weiter; umgekehrt eins zurück (dann verwirft die Plausibilität).
    """
    ganz = math.floor(letzter)
    d = nachkomma - (letzter - ganz)
    return ganz + 1 if d < -0.5 else ganz - 1 if d > 0.5 else ganz


def _wickeln(d: float) -> float:
    d %= 10
    return d - 10 if d > 5 else d


@dataclass
class Stelle:
    name: str
    wert: float | None
    ki: list = field(default_factory=list)       # je Foto
    spitze: list = field(default_factory=list)   # je Foto (nur Zeiger)
    hinweis: str = ""


@dataclass
class Ergebnis:
    wert: float | None
    roh: str
    vertrauen: int
    gruende: list
    ziffern: list
    zeiger: list
    ausrichtung: list
    bild: np.ndarray | None  # erstes ausgerichtetes Bild (RGB), für Anzeige
    rollen_klar: bool = True  # False: mindestens ein Foto mit beschlagenen Rollen
    rollen_kontrast: float | None = None  # schwächste Rolle im Verhältnis zum Referenzbild

    def als_dict(self) -> dict:
        def st(s):
            return {"name": s.name, "wert": None if s.wert is None else round(s.wert, 2),
                    "ki": [None if v is None else round(v, 2) for v in s.ki],
                    "spitze": [None if v is None else round(v, 2) for v in s.spitze],
                    **({"hinweis": s.hinweis} if s.hinweis else {})}
        return {"wert": self.wert, "roh": self.roh, "vertrauen": self.vertrauen, "gruende": self.gruende,
                "ziffern": [st(s) for s in self.ziffern], "zeiger": [st(s) for s in self.zeiger],
                "ausrichtung": self.ausrichtung, "rollen_klar": self.rollen_klar,
                "rollen_kontrast": None if self.rollen_kontrast is None else round(self.rollen_kontrast, 2)}


def lade_rgb(pfad) -> np.ndarray:
    bild = cv2.imread(str(pfad))
    if bild is None:
        raise FileNotFoundError(pfad)
    return cv2.cvtColor(bild, cv2.COLOR_BGR2RGB)


class Leser:
    def __init__(self, k):
        self.k = k
        self.referenz = lade_rgb(k.referenzbild)
        self.ausrichter = Ausrichter(self.referenz, arbeitsbreite=self.referenz.shape[1])
        self.m_ziffern = Modell(k.modell_ziffern)
        self.m_zeiger = Modell(k.modell_zeiger)
        self.ref_kontrast = [max(kontrast(ausschneiden(self.referenz, r)), 1.0) for r in k.ziffern]

    def lies(self, bilder_rgb: list[np.ndarray], letzter: float | None = None) -> Ergebnis:
        """Jedes Foto wird für sich komplett ausgewertet, dann zählt der Median der Gesamtwerte.

        Je Stelle über die Fotos zu mitteln geht schief, wenn gerade Wasser läuft: der
        x0.0001-Zeiger dreht sich bei 6 L/min einmal in 10 s, zwischen den Fotos also
        ein ganzes Stück – die Stellen würden aus verschiedenen Zeitpunkten gemischt.
        """
        ausgerichtet, infos = [], []
        for b in bilder_rgb:
            a, info = self.ausrichter.ausrichten(b)
            infos.append(info)
            if a is not None:
                ausgerichtet.append(a)
        if not ausgerichtet:
            return Ergebnis(None, "", 0, ["Ausrichtung fehlgeschlagen: " + infos[0].get("fehler", "?")],
                            [], [], infos, None)

        einzeln = [self._lies_foto(a, letzter) for a in ausgerichtet]
        gueltig = [e for e in einzeln if e.wert is not None]
        if not gueltig:
            e = einzeln[0]
            return Ergebnis(None, e.roh, 0, e.gruende, *self._stellen(einzeln, e), infos, ausgerichtet[0],
                            all(x.rollen_klar for x in einzeln), e.rollen_kontrast)

        werte = sorted(e.wert for e in gueltig)
        mitte = werte[(len(werte) - 1) // 2]
        beste = next(e for e in gueltig if e.wert == mitte)
        vertrauen, gruende = beste.vertrauen, list(beste.gruende)

        if len(ausgerichtet) < len(bilder_rgb):
            gruende.append(f"{len(bilder_rgb) - len(ausgerichtet)} Foto(s) nicht ausrichtbar")
        if len(gueltig) * 2 <= len(bilder_rgb):
            vertrauen -= 30
            gruende.append(f"nur {len(gueltig)} von {len(bilder_rgb)} Fotos lesbar")
        # Zwischen den Fotos liegen ein paar Sekunden – bei 5 m³/h sind das höchstens ~0.005 m³
        abw = max(abs(w - mitte) for w in werte)
        if abw > 0.01:
            vertrauen -= 30
            gruende.append("Fotos uneinig: " + " / ".join(f"{w:.4f}" for w in werte))
        ziffern, zeiger = self._stellen(einzeln, beste)
        return Ergebnis(mitte, beste.roh, int(max(0, vertrauen)), gruende, ziffern, zeiger, infos,
                        ausgerichtet[einzeln.index(beste)], all(e.rollen_klar for e in einzeln),
                        min((e.rollen_kontrast for e in einzeln if e.rollen_kontrast is not None), default=None))

    def _lies_foto(self, a: np.ndarray, letzter: float | None) -> Ergebnis:
        gruende = []
        ziffern, verhaeltnis = [], None
        for r, ref in zip(self.k.ziffern, self.ref_kontrast):
            c = ausschneiden(a, r)
            v = self.m_ziffern.lies(c, r.name, self.k.ziffer_mindestsicherheit).wert
            ziffern.append(Stelle(r.name, v, [v]))
            q = kontrast(c) / ref
            verhaeltnis = q if verhaeltnis is None else min(verhaeltnis, q)
        klar = verhaeltnis is None or verhaeltnis >= self.k.rollen_mindestkontrast
        if not klar:
            for z in ziffern:
                z.wert, z.hinweis = None, "beschlagen"
        zeiger = []
        for r in self.k.zeiger:
            c = ausschneiden(a, r)
            sp = lies_spitze(c, r.name)
            zeiger.append(Stelle(r.name, None, [self.m_zeiger.lies(c, r.name).wert],
                                 [sp.wert if sp.wert is not None and sp.sicherheit >= 0.3 else None]))
        self._zeiger_zusammenfuehren(zeiger, gruende)
        vertrauen = self._vertrauen(ziffern if klar else [], zeiger, gruende)
        if klar:
            wert, roh = zusammensetzen([z.wert for z in ziffern], [z.wert for z in zeiger], letzter)
        else:
            nachkomma, roh_nk = zusammensetzen([], [z.wert for z in zeiger])
            gruende.append(f"Rollen beschlagen (Kontrast {verhaeltnis:.0%} der Referenz)")
            if letzter is None:
                wert, roh = None, "B" * len(ziffern) + roh_nk
            else:
                ganz = ganze_aus_letztem(nachkomma, letzter)
                wert = round(ganz + nachkomma, len(zeiger))
                roh = str(ganz).zfill(len(ziffern))[-len(ziffern):] + roh_nk
                vertrauen -= 10
                gruende.append("ganze m³ aus dem letzten Stand")
        if wert is None:
            vertrauen = 0
            gruende.append("Rolle unlesbar" if klar else "kein letzter Stand für die beschlagenen Rollen")
        return Ergebnis(wert, roh, max(0, vertrauen), gruende, ziffern, zeiger, [], a, klar, verhaeltnis)

    @staticmethod
    def _stellen(einzeln: list[Ergebnis], beste: Ergebnis) -> tuple[list, list]:
        """Stellen zur Anzeige: Wert und Hinweis vom Median-Foto, KI/Spitze aller Fotos."""
        def mischen(art):
            aus = []
            for i, s in enumerate(getattr(beste, art)):
                ki = [getattr(e, art)[i].ki[0] for e in einzeln]
                sp = [getattr(e, art)[i].spitze[0] for e in einzeln] if s.spitze else []
                aus.append(Stelle(s.name, s.wert, ki, sp, s.hinweis))
            return aus
        return mischen("ziffern"), mischen("zeiger")

    def _zeiger_zusammenfuehren(self, zeiger: list[Stelle], gruende: list):
        # von der kleinsten Stelle (rechts) nach links: die kleinste hat keinen Nachfolger
        for i in range(len(zeiger) - 1, -1, -1):
            z = zeiger[i]
            nach = zeiger[i + 1].wert if i + 1 < len(zeiger) else None
            ki, sp = z.ki[0], z.spitze[0]
            if ki is None and sp is None:
                z.hinweis = "unlesbar"
                continue
            if ki is None or sp is None:
                z.wert = ki if sp is None else sp
                z.hinweis = "nur " + ("KI" if sp is None else "Spitze")
                continue
            if kreis_abstand(ki, sp) <= self.k.max_abweichung_methoden:
                # Spitze ist feiner (0.01 statt 0.1 Auflösung), KI fängt grobe Ausreißer
                z.wert = sp if kreis_abstand(ki, sp) <= 0.3 else kreis_mittel(ki, sp)
                continue
            # Widerspruch: was passt besser zum Nachfolger?
            if nach is not None:
                versatz = self.k.ketten_versatz.get(z.name, 0.0)
                z.wert = min((ki, sp), key=lambda v: abs(_wickeln(ketten_rest(v, nach) - versatz)))
                z.hinweis = f"KI {ki:.1f} / Spitze {sp:.1f} uneinig, Kette entschied {z.wert:.1f}"
            else:
                z.wert = sp
                z.hinweis = f"KI {ki:.1f} / Spitze {sp:.1f} uneinig, Spitze genommen"
            gruende.append(f"{z.name}: {z.hinweis}")

    def _vertrauen(self, ziffern: list[Stelle], zeiger: list[Stelle], gruende: list) -> int:
        v = 100.0
        for z in zeiger:
            if z.wert is None:
                v -= 60
                gruende.append(f"{z.name} unlesbar")
                continue
            if "uneinig" in z.hinweis:
                v -= 25
            elif z.hinweis.startswith("nur"):
                v -= 15
                gruende.append(f"{z.name}: {z.hinweis}")
        for i in range(len(zeiger) - 1):
            a, b = zeiger[i], zeiger[i + 1]
            if a.wert is None or b.wert is None:
                continue
            rest = _wickeln(ketten_rest(a.wert, b.wert) - self.k.ketten_versatz.get(a.name, 0.0))
            if abs(rest) > self.k.max_kettenrest:
                v -= 20
                gruende.append(f"{a.name}→{b.name} passt nicht zusammen (Rest {rest:.1f})")
        for z in ziffern:
            if z.wert is None:
                v -= 30
                gruende.append(f"Rolle {z.name} unlesbar")
        return int(max(0, min(100, round(v))))


def markieren(bild_rgb: np.ndarray, k, ergebnis: Ergebnis | None = None) -> np.ndarray:
    """Lesebereiche mit erkannten Werten einzeichnen (für Webseite und HA-Kamerabild)."""
    aus = bild_rgb.copy()
    lesungen = {}
    if ergebnis:
        lesungen = {s.name: s for s in ergebnis.ziffern + ergebnis.zeiger}
    for r, farbe in [(r, (40, 90, 255)) for r in k.ziffern] + [(r, (40, 220, 60)) for r in k.zeiger]:
        s = lesungen.get(r.name)
        if s is not None and s.hinweis:
            farbe = (255, 160, 0)
        cv2.rectangle(aus, (r.x, r.y), (r.x + r.b, r.y + r.h), farbe, 1)
        if s is not None:
            text = "?" if s.wert is None else f"{s.wert:.1f}" if r in k.ziffern else f"{s.wert:.2f}"
            cv2.putText(aus, text, (r.x, r.y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, farbe, 1, cv2.LINE_AA)
    return aus
