"""Ganze Kette mit echten Bildern der ESP32-CAM vom 24.10.2026 (Stand 404.7274 m³, von Hand geprüft).

Vorher meldete der ESP32 aus solchen Bildern 405.8 und blieb dann hängen.
"""

from pathlib import Path

import pytest

pytest.importorskip("cv2")
pytest.importorskip("ai_edge_litert")

from wasserzaehler import konfig  # noqa: E402
from wasserzaehler.kamera import Kamera  # noqa: E402
from wasserzaehler.leser import Leser, kreis_abstand, kreis_median, ketten_rest  # noqa: E402
from wasserzaehler.zeiger_cv import lies_zeiger  # noqa: E402

HIER = Path(__file__).parent
BILDER = sorted((HIER / "testdaten").glob("raw_*.jpg"))  # Seriennummer unkenntlich gemacht


@pytest.fixture(scope="module")
def k():
    k = konfig.lade(HIER / "testdaten" / "test.toml")
    if not (k.modell_ziffern.exists() and k.modell_zeiger.exists()):
        pytest.skip("Modelle fehlen in modelle/ (siehe docs: Modelle beschaffen)")
    return k


@pytest.fixture(scope="module")
def leser(k):
    return Leser(k)


@pytest.fixture(scope="module")
def gedreht(k):
    kam = Kamera(k.kamera)
    return [kam.vorbereiten(p.read_bytes()) for p in BILDER]


def test_kreisrechnung():
    assert kreis_abstand(9.9, 0.1) == pytest.approx(0.2)
    assert kreis_median([9.8, 0.1, 9.9]) == 9.9
    assert ketten_rest(2.43, 4.3) == pytest.approx(0.0)
    assert ketten_rest(2.43, 7.35) == pytest.approx(-3.05)
    assert ketten_rest(7.98, 0.2) == pytest.approx(-0.4)  # über den Nullpunkt


@pytest.mark.parametrize("i", range(len(BILDER)))
def test_einzelbild(leser, gedreht, i):
    e = leser.lies([gedreht[i]])
    assert e.wert == 404.7274, (e.roh, e.gruende)
    assert e.vertrauen >= 80, e.gruende


def test_drei_fotos(leser, gedreht):
    e = leser.lies(gedreht)
    assert e.wert == 404.7274
    assert e.vertrauen == 100, e.gruende
    assert not any(s.hinweis for s in e.zeiger)


def test_spitze_findet_alle_zeiger(leser, gedreht, k):
    a, _ = leser.ausrichter.ausrichten(gedreht[0])
    erwartet = {"x0.1": 7.2, "x0.01": 2.65, "x0.001": 7.3, "x0.0001": 4.45}
    for r in k.zeiger:
        l = lies_zeiger(a[r.y:r.y + r.h, r.x:r.x + r.b], r.name)
        assert kreis_abstand(l.wert, erwartet[r.name]) < 0.15, (r.name, l.wert)
        assert l.sicherheit > 0.5


def test_verdrehter_zeiger_wird_erkannt(leser, gedreht, k):
    """KI liest einen Zeiger um 180° falsch (der alte ESP32-Fehler) → Spitze + Kette retten den Wert."""
    import numpy as np
    m = leser.m_zeiger
    echt = m.lies

    def falsch(ausschnitt, name="", mindestsicherheit=0.0):
        l = echt(ausschnitt, name)
        if name == "x0.001":
            l.wert = (l.wert + 5) % 10
        return l
    m.lies = falsch
    try:
        e = leser.lies(gedreht)
    finally:
        m.lies = echt
    assert e.wert == 404.7274
    assert e.vertrauen < 100 and any("x0.001" in g for g in e.gruende)
    assert np.isfinite(e.vertrauen)


# Messungen aus dem Archiv vom 24./25.10.2026, Werte durch die Rohwerte des ESP32 bestätigt
# (080457: während Wasser lief, ESP32 eine Minute früher 404.7910)
ARCHIV = {
    "2026-10-24/233621": 404.7274, "2026-10-25/001642": 404.7320, "2026-10-25/002153": 404.7325,
    "2026-10-25/002703": 404.7364, "2026-10-25/020226": 404.7395, "2026-10-25/043746": 404.7434,
    "2026-10-25/062633": 404.7521, "2026-10-25/074414": 404.7560, "2026-10-25/074925": 404.7807,
    "2026-10-25/080457": 404.8008,
}


@pytest.mark.parametrize("ordner", sorted(ARCHIV))
def test_archiv(leser, k, ordner):
    kam = Kamera(k.kamera)
    fotos = sorted((HIER / "testdaten" / "archiv" / ordner).glob("foto*.jpg"))
    e = leser.lies([kam.vorbereiten(f.read_bytes()) for f in fotos])
    assert e.wert == pytest.approx(ARCHIV[ordner], abs=0.0006), (e.roh, e.gruende)
    assert e.vertrauen >= 80, e.gruende
