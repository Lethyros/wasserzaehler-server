"""Konfiguration aus config.toml laden (Passwörter kommen aus der Umgebung)."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Roi:
    name: str
    x: int
    y: int
    b: int  # Breite
    h: int  # Höhe


@dataclass
class Konfig:
    basis: Path
    referenzbild: Path
    ziffern: list[Roi]
    zeiger: list[Roi]
    modell_ziffern: Path
    modell_zeiger: Path
    ziffer_mindestsicherheit: float = 0.0
    max_abweichung_methoden: float = 1.0   # KI und Spitze dürfen so weit auseinander liegen (Zeigereinheiten)
    max_kettenrest: float = 2.5            # Zeiger → Nachfolger, nach Abzug des Versatzes (Einheiten des Nachfolgers)
    ketten_versatz: dict = field(default_factory=dict)
    intervall_s: int = 300
    bilder_pro_messung: int = 3
    max_durchfluss_m3h: float = 5.0
    neuabgleich_nach: int = 3
    mindestvertrauen: int = 50             # darunter wird nichts veröffentlicht
    archiv: Path = Path("/var/lib/wasserzaehler/archiv")
    archiv_tage: int = 90
    zustandsdatei: Path = Path("/var/lib/wasserzaehler/zustand.json")
    kamera: dict = field(default_factory=dict)
    mqtt: dict = field(default_factory=dict)
    web: dict = field(default_factory=dict)


def _rois(liste) -> list[Roi]:
    return [Roi(r["name"], *r["rechteck"]) for r in liste]


def lade(pfad: str | Path) -> Konfig:
    pfad = Path(pfad).resolve()
    with open(pfad, "rb") as f:
        d = tomllib.load(f)
    basis = pfad.parent

    def p(x):
        x = Path(x)
        return x if x.is_absolute() else basis / x

    z, m, a = d["zaehler"], d.get("messung", {}), d.get("archiv", {})
    k = Konfig(
        basis=basis,
        referenzbild=p(z["referenzbild"]),
        ziffern=_rois(z.get("ziffern", [])),
        zeiger=_rois(z.get("zeiger", [])),
        modell_ziffern=p(z["modell_ziffern"]),
        modell_zeiger=p(z["modell_zeiger"]),
        ziffer_mindestsicherheit=z.get("ziffer_mindestsicherheit", 0.0),
        max_abweichung_methoden=z.get("max_abweichung_methoden", 1.0),
        max_kettenrest=z.get("max_kettenrest", 2.5),
        ketten_versatz=dict(z.get("ketten_versatz", {})),
        intervall_s=m.get("intervall_s", 300),
        bilder_pro_messung=m.get("bilder_pro_messung", 3),
        max_durchfluss_m3h=m.get("max_durchfluss_m3h", 5.0),
        neuabgleich_nach=m.get("neuabgleich_nach", 3),
        mindestvertrauen=m.get("mindestvertrauen", 50),
        archiv=p(a.get("pfad", "/var/lib/wasserzaehler/archiv")),
        archiv_tage=a.get("tage", 90),
        zustandsdatei=p(a.get("zustandsdatei", "/var/lib/wasserzaehler/zustand.json")),
        kamera=d.get("kamera", {}),
        mqtt=d.get("mqtt", {}),
        web=d.get("web", {}),
    )
    # Zugangsdaten nie in config.toml, sondern in /etc/wasserzaehler.env (EnvironmentFile)
    k.mqtt.setdefault("benutzer", os.environ.get("WASSERZAEHLER_MQTT_BENUTZER", ""))
    k.mqtt.setdefault("passwort", os.environ.get("WASSERZAEHLER_MQTT_PASSWORT", ""))
    return k
