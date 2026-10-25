"""Einrichtung aus einem laufenden AI-on-the-edge-Gerät übernehmen.

Holt von der ESP32-CAM:
  - config.ini  → Drehung (InitialRotate), Lesebereiche der Ziffern und Zeiger, Modellnamen
  - reference.jpg → Referenzbild (bereits gedreht, dazu passen die Lesebereiche)
  - die beiden .tflite-Modelle
und schreibt daraus config.toml, referenz.jpg und modelle/ in den Zielordner.

Die Modelle stehen unter der Lizenz von AI-on-the-edge (nur privat, nicht
kommerziell) und werden deshalb nicht mit diesem Projekt verteilt, sondern
vom eigenen Gerät geholt.
"""

import re
import urllib.request
from pathlib import Path


def _holen(host: str, pfad: str) -> bytes:
    with urllib.request.urlopen(f"http://{host}/fileserver{pfad}", timeout=60) as r:
        return r.read()


def lies_config_ini(text: str, zahl: str | None = None) -> dict:
    """Die für uns wichtigen Teile der config.ini von AI-on-the-edge (ab v15) lesen.

    Rückgabe: {"drehung": float, "modell_ziffern": "/config/…", "modell_zeiger": …,
               "ziffern": [(name, x, y, b, h)], "zeiger": [(name, x, y, b, h)], "zahl": "main"}
    """
    aus = {"drehung": 0.0, "modell_ziffern": None, "modell_zeiger": None, "ziffern": [], "zeiger": []}
    abschnitt = None
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        if zeile.startswith("[") or zeile.startswith(";["):
            abschnitt = zeile.lstrip(";").strip("[]").lower() if not zeile.startswith(";") else None
            continue
        if zeile.startswith(";") or abschnitt is None:
            continue
        teile = zeile.replace("=", " ").split()
        if abschnitt == "alignment" and teile[0].lower() == "initialrotate":
            aus["drehung"] = float(teile[1])
        elif abschnitt in ("digits", "analog"):
            art = "ziffern" if abschnitt == "digits" else "zeiger"
            if teile[0].lower() == "model":
                aus["modell_" + art] = teile[1]
            elif re.fullmatch(r"[^.\s]+\.[^.\s]+", teile[0]) and len(teile) >= 5:
                nummer, name = teile[0].split(".", 1)
                aus[art].append((nummer, name, *map(int, teile[1:5])))
    nummern = [n for n, *_ in aus["ziffern"] + aus["zeiger"]]
    if not nummern:
        raise ValueError("Keine Lesebereiche in der config.ini gefunden")
    zahl = zahl or nummern[0]
    for art in ("ziffern", "zeiger"):
        aus[art] = [tuple(r[1:]) for r in aus[art] if r[0] == zahl]
    aus["zahl"] = zahl
    return aus


VORLAGE = """# wasserzaehler – Konfiguration, übernommen von {host} (Zahl "{zahl}")
# MQTT-Benutzer und -Passwort stehen NICHT hier, sondern in /etc/wasserzaehler.env

[kamera]
host = "{host}"
drehung_grad = {drehung}
pause_zwischen_fotos_s = 1.0

[zaehler]
referenzbild = "referenz.jpg"
modell_ziffern = "modelle/{mz}"
modell_zeiger = "modelle/{ma}"
max_abweichung_methoden = 1.0
max_kettenrest = 2.5

# Rechteck = [x, y, Breite, Höhe] im Referenzbild. Ziffern von der höchsten Stelle nach rechts,
# Zeiger in der Reihenfolge x0.1, x0.01, x0.001, …
ziffern = [
{ziffern}
]
zeiger = [
{zeiger}
]

# Fester Versatz Zeiger → Nachfolger, nach ein paar Tagen mit "wasserzaehler kalibrieren" bestimmen
[zaehler.ketten_versatz]

[messung]
intervall_s = 300
bilder_pro_messung = 3
max_durchfluss_m3h = 5.0
neuabgleich_nach = 3
mindestvertrauen = 50

[archiv]
pfad = "/var/lib/wasserzaehler/archiv"
tage = 90
zustandsdatei = "/var/lib/wasserzaehler/zustand.json"

[mqtt]
host = ""                     # leer = kein MQTT
port = 1883
basis = "wasserzaehler"
client_id = "wasserzaehler-server"
discovery_praefix = "homeassistant"
vergleich_topic = ""          # z. B. "wassermeter/main/value", um den Wert des ESP32 mitzulesen

[web]
port = 8080
"""


def uebernehmen(host: str, ziel: Path, zahl: str | None = None, ueberschreiben: bool = False) -> Path:
    ziel = Path(ziel)
    datei = ziel / "config.toml"
    if datei.exists() and not ueberschreiben:
        raise FileExistsError(f"{datei} gibt es schon (--ueberschreiben zum Ersetzen)")
    ini = lies_config_ini(_holen(host, "/config/config.ini").decode("utf-8", "replace"), zahl)
    if not ini["ziffern"] or not ini["zeiger"] or not ini["modell_ziffern"] or not ini["modell_zeiger"]:
        raise ValueError("Dieses Projekt braucht Ziffern UND Zeiger (Zähler mit Rollen und roten Zeigern)")

    (ziel / "modelle").mkdir(parents=True, exist_ok=True)
    namen = {}
    for art in ("ziffern", "zeiger"):
        pfad = ini["modell_" + art]
        name = pfad.rsplit("/", 1)[-1]
        (ziel / "modelle" / name).write_bytes(_holen(host, pfad if pfad.startswith("/") else "/config/" + pfad))
        namen[art] = name
    (ziel / "referenz.jpg").write_bytes(_holen(host, "/config/reference.jpg"))

    def zeilen(rois):
        return "\n".join(f'  {{ name = "{n}", rechteck = [{x}, {y}, {b}, {h}] }},' for n, x, y, b, h in rois)

    datei.write_text(VORLAGE.format(host=host, zahl=ini["zahl"], drehung=ini["drehung"],
                                    mz=namen["ziffern"], ma=namen["zeiger"],
                                    ziffern=zeilen(ini["ziffern"]), zeiger=zeilen(ini["zeiger"])))
    return datei
