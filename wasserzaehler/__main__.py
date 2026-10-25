"""Aufruf:  python -m wasserzaehler [-c config.toml] <befehl>

  uebernehmen HOST  config.toml, referenz.jpg und Modelle von einer AI-on-the-edge-Kamera holen
  dienst          Dauerbetrieb (systemd): messen, archivieren, MQTT, Webseite
  lies BILD...    Rohbilder vom ESP32 auslesen (ungedreht, wie im Archiv); mehrere = eine Messung
  kalibrieren     festen Versatz der Zeiger zueinander aus dem Archiv bestimmen
  foto [-o DATEI] ein Foto holen und gedreht speichern (z. B. als neues Referenzbild)
"""

import argparse
import json
import logging
import signal
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

from . import __version__, konfig
from .auswertung import Plausibilitaet
from .kamera import Kamera
from .leser import Leser, ketten_rest, markieren

log = logging.getLogger("wasserzaehler")


def jpeg(bild_rgb, qualitaet=85) -> bytes:
    return cv2.imencode(".jpg", cv2.cvtColor(bild_rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, qualitaet])[1].tobytes()


class Dienst:
    def __init__(self, k: konfig.Konfig):
        from .archiv import Archiv
        from .mqtt_ha import HaMqtt
        from .web import Web

        self.k = k
        self.leser = Leser(k)
        self.kamera = Kamera(k.kamera)
        self.archiv = Archiv(k.archiv, k.archiv_tage)
        self.plaus = Plausibilitaet(k.max_durchfluss_m3h, k.neuabgleich_nach)
        self.mqtt = HaMqtt(k.mqtt, __version__) if k.mqtt.get("host") else None
        self.sofort = threading.Event()
        self.lock = threading.Lock()
        self.ende = threading.Event()
        self.zustand: dict = {"zaehlerstand": None, "status": "startet"}
        self.bilder = {"referenz.jpg": jpeg(self.leser.referenz)}
        self._zustand_laden()
        self.web = Web(k.web, self)

    # --- Zustand über Neustarts retten (zusätzlich zum retained MQTT-Wert) ---
    def _zustand_laden(self):
        try:
            d = json.loads(self.k.zustandsdatei.read_text())
            self.plaus.letzter, self.plaus.letzte_zeit = d["letzter"], d["letzte_zeit"]
            self.zustand["zaehlerstand"] = d["letzter"]
            log.info("Letzter Stand aus %s: %.4f", self.k.zustandsdatei, d["letzter"])
        except (OSError, ValueError, KeyError):
            pass

    def _zustand_sichern(self):
        if self.plaus.letzter is None:
            return
        self.k.zustandsdatei.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.k.zustandsdatei.with_suffix(".tmp")
        tmp.write_text(json.dumps({"letzter": self.plaus.letzter, "letzte_zeit": self.plaus.letzte_zeit}))
        tmp.replace(self.k.zustandsdatei)

    def setzen(self, wert: float):
        with self.lock:
            self.plaus.letzter, self.plaus.letzte_zeit = wert, time.time()
            self.plaus.kandidaten.clear()
            self._zustand_sichern()
        self.zustand.update(zaehlerstand=wert, status="von Hand gesetzt")
        if self.mqtt:
            self.mqtt.zaehlerstand(wert)
        log.info("Zählerstand von Hand gesetzt: %.4f", wert)

    def messen(self):
        with self.lock:
            beginn = time.time()
            zeit = datetime.now().astimezone()
            fotos = self.kamera.fotos(self.k.bilder_pro_messung)
            e = self.leser.lies([b for _, b in fotos], self.plaus.letzter)
            vorher, vorher_zeit = self.plaus.letzter, self.plaus.letzte_zeit

            if e.wert is None:
                ergebnis, status = None, "unlesbar: " + "; ".join(e.gruende)
            elif e.vertrauen < self.k.mindestvertrauen:
                ergebnis, status = None, f"unsicher ({e.vertrauen} %): " + "; ".join(e.gruende)
            else:
                ergebnis, status = self.plaus.pruefe(e.wert)

            durchfluss = None
            if ergebnis is not None:
                durchfluss = 0.0
                if vorher is not None and vorher_zeit and ergebnis != vorher:
                    durchfluss = round((ergebnis - vorher) * 1000 / max((time.time() - vorher_zeit) / 60, 0.1), 2)
                self._zustand_sichern()

            esp32 = self.mqtt.esp32_wert if self.mqtt else None
            self.zustand = {
                "zaehlerstand": self.plaus.letzter, "gelesen": e.wert, "roh": e.roh, "vertrauen": e.vertrauen,
                "status": status, "gruende": e.gruende, "durchfluss_l_min": durchfluss,
                "esp32": esp32, "zeit": zeit.isoformat(timespec="seconds"),
                "dauer_s": round(time.time() - beginn, 1),
                "verschiebung": [i.get("verschiebung") for i in e.ausrichtung],
            }
            ordner = self.archiv.ablegen(zeit, [j for j, _ in fotos],
                                         {**e.als_dict(), "zeit": self.zustand["zeit"], "status": status,
                                          "veroeffentlicht": ergebnis, "esp32": esp32})
            self.zustand["archiv"] = ordner
            if e.bild is not None:
                self.bilder["aktuell.jpg"] = jpeg(markieren(e.bild, self.k, e))
            self.bilder["roh.jpg"] = fotos[0][0]
            log.info("Messung: %s (%s %%) → %s [%s] roh=%s", e.wert, e.vertrauen, ergebnis, status, e.roh)
            if self.mqtt:
                if ergebnis is not None:
                    self.mqtt.zaehlerstand(ergebnis)
                self.mqtt.zustand(self.zustand)
                if "aktuell.jpg" in self.bilder:
                    self.mqtt.bild(self.bilder["aktuell.jpg"])

    def laufen(self):
        self.web.starten()
        if self.mqtt:
            self.mqtt.bei_lesen = self.sofort.set
            self.mqtt.bei_setzen = self.setzen
            self.mqtt.starten()
            vorwert = self.mqtt.warte_auf_vorwert()
            if self.plaus.letzter is None and vorwert is not None:
                self.plaus.letzter, self.plaus.letzte_zeit = vorwert, time.time()
                self.zustand["zaehlerstand"] = vorwert
                log.info("Vorwert vom Broker: %.4f", vorwert)
        letztes_aufraeumen = 0.0
        while not self.ende.is_set():
            try:
                self.messen()
            except Exception as ex:
                log.exception("Messung fehlgeschlagen")
                self.zustand.update(status=f"Fehler: {ex}", zeit=datetime.now().astimezone().isoformat(timespec="seconds"))
                if self.mqtt:
                    self.mqtt.zustand(self.zustand)
            if time.time() - letztes_aufraeumen > 86400:
                self.archiv.aufraeumen()
                letztes_aufraeumen = time.time()
            self.sofort.wait(self.k.intervall_s)
            self.sofort.clear()
        if self.mqtt:
            self.mqtt.beenden()


def kalibrieren(k: konfig.Konfig):
    from .archiv import Archiv
    reste: dict[str, list[float]] = {z.name: [] for z in k.zeiger[:-1]}
    positionen: dict[str, set] = {z.name: set() for z in k.zeiger[:-1]}
    anzahl = 0
    for e in Archiv(k.archiv, k.archiv_tage).alle_ergebnisse():
        z = e.get("zeiger", [])
        if len(z) != len(k.zeiger) or any(s.get("wert") is None or s.get("hinweis") for s in z):
            continue
        anzahl += 1
        for a, b in zip(z, z[1:]):
            reste[a["name"]].append(ketten_rest(a["wert"], b["wert"]))
            positionen[a["name"]].add(int(b["wert"]))
    if anzahl < 20:
        print(f"Erst {anzahl} brauchbare Messungen im Archiv – mindestens 20 nötig.")
        return
    print(f"{anzahl} Messungen ausgewertet. Vorschlag für config.toml:\n\n[zaehler.ketten_versatz]")
    for name, r in reste.items():
        print(f'"{name}" = {statistics.median(r):.1f}   '
              f'# Streuung ±{statistics.pstdev(r):.1f}, Nachfolger auf {len(positionen[name])}/10 Stellungen gesehen')
    print("\nWenig gesehene Stellungen = Wert noch unsicher; nach mehr Wasserverbrauch erneut laufen lassen.")


def main():
    ap = argparse.ArgumentParser(prog="wasserzaehler")
    ap.add_argument("-c", "--config", default="/opt/wasserzaehler/config.toml")
    ap.add_argument("-v", "--ausfuehrlich", action="store_true")
    sub = ap.add_subparsers(dest="befehl", required=True)
    u = sub.add_parser("uebernehmen")
    u.add_argument("host", help="IP/Name der ESP32-CAM mit AI-on-the-edge")
    u.add_argument("--zahl", help="Name der Zahl in der config.ini (Standard: die erste, meist main)")
    u.add_argument("--ziel", default=None, help="Zielordner (Standard: Ordner der config.toml)")
    u.add_argument("--ueberschreiben", action="store_true")
    sub.add_parser("dienst")
    sub.add_parser("kalibrieren")
    f = sub.add_parser("foto")
    f.add_argument("-o", "--ausgabe", default="foto.jpg")
    l = sub.add_parser("lies")
    l.add_argument("bilder", nargs="+")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.ausfuehrlich else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if a.befehl == "uebernehmen":
        from .einrichtung import uebernehmen
        datei = uebernehmen(a.host, Path(a.ziel or Path(a.config).parent), a.zahl, a.ueberschreiben)
        print(f"geschrieben: {datei} (+ referenz.jpg, modelle/) – MQTT-Host noch eintragen, dann Dienst starten")
        return
    k = konfig.lade(a.config)

    if a.befehl == "dienst":
        d = Dienst(k)
        signal.signal(signal.SIGTERM, lambda *_: (d.ende.set(), d.sofort.set()))
        d.laufen()
    elif a.befehl == "kalibrieren":
        kalibrieren(k)
    elif a.befehl == "foto":
        kam = Kamera(k.kamera)
        bild = kam.vorbereiten(kam.roh())
        cv2.imwrite(a.ausgabe, cv2.cvtColor(bild, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
        print(f"gespeichert: {a.ausgabe} ({bild.shape[1]}x{bild.shape[0]}, gedreht um {kam.drehung}°)")
    elif a.befehl == "lies":
        kam, leser = Kamera(k.kamera), Leser(k)
        e = leser.lies([kam.vorbereiten(Path(p).read_bytes()) for p in a.bilder])
        print(f"Wert {e.wert}  roh={e.roh}  Vertrauen {e.vertrauen} %")
        for g in e.gruende:
            print("  -", g)
        for s in e.ziffern + e.zeiger:
            w = "?" if s.wert is None else f"{s.wert:4.2f}"
            print(f"   {s.name:8s} {w}  KI={s.ki}  Spitze={[round(v, 2) if v is not None else None for v in s.spitze]} {s.hinweis}")
        if e.bild is not None:
            ziel = Path(a.bilder[0]).with_name(Path(a.bilder[0]).stem + "_gelesen.jpg")
            ziel.write_bytes(jpeg(markieren(e.bild, k, e)))
            print("markiert:", ziel)


if __name__ == "__main__":
    main()
