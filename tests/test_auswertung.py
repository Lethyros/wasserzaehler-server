from wasserzaehler.auswertung import Plausibilitaet, stelle, zusammensetzen


def test_stelle_ohne_vorgaenger():
    assert stelle(6.4, None) == 6
    assert stelle(9.99, None) == 9


def test_rolle_kurz_vor_dem_weiterdrehen():
    # Nachbarrolle bei 9.9 → diese Rolle ist erst halb weiter, bleibt 6
    assert stelle(6.95, 9.9) == 6
    assert stelle(7.05, 9.9) == 6


def test_rolle_gerade_umgesprungen():
    # Nachbarrolle schon wieder bei 0.1 → diese Rolle steht auf 7
    assert stelle(6.97, 0.1) == 7


def test_halb_gedrehte_rolle_mitte():
    # mitlaufende Rolle: Nachbar bei 5 → 6.5 ist eine 6
    assert stelle(6.5, 5.0) == 6


def test_unscharfe_null_kippt_nicht():
    # Fall aus dem ESP32-Bild: „0“ wird als 0.63 gelesen, Nachbar bei 0.06
    assert stelle(0.63, 0.06) == 0


def test_umlauf_9_auf_0():
    assert stelle(9.97, 0.2) == 0
    assert stelle(0.05, 9.95) == 9


def test_zusammensetzen_esp32_werte():
    wert, roh = zusammensetzen([0.63, 0.06, 3.84, 9.94, 1.02], [0.42, 4.69, 0.84, 1.28])
    assert roh == "00401.0511"
    assert wert == 401.0511


def test_unlesbare_rolle_aus_vorwert():
    wert, roh = zusammensetzen([0.0, None, 4.0, 0.0, 1.0], [0.4, 4.7, 0.8, 1.3], letzter=401.04)
    assert wert == 401.0511
    wert, roh = zusammensetzen([0.0, None, 4.0, 0.0, 1.0], [0.4, 4.7, 0.8, 1.3])
    assert wert is None and roh.startswith("0N")


def test_plausibilitaet():
    p = Plausibilitaet(max_durchfluss_m3h=4.0, neuabgleich_nach=3)
    t = 1_000_000.0
    assert p.pruefe(401.05, t)[0] == 401.05
    assert p.pruefe(401.06, t + 300)[0] == 401.06            # 10 L in 5 min: ok
    assert p.pruefe(401.0595, t + 600)[0] == 401.06          # Rauschen rückwärts
    assert p.pruefe(716.05, t + 900)[0] is None              # Sprung → verworfen
    assert p.pruefe(401.07, t + 1200)[0] == 401.07           # danach normal weiter


def test_neuabgleich_haengt_nicht_fest():
    # ESP32-Problem: falscher Vorwert 394 → hing seit Tagen fest. Hier: nach 3 stimmigen Messungen übernommen.
    p = Plausibilitaet(max_durchfluss_m3h=4.0, neuabgleich_nach=3)
    t = 0.0
    p.pruefe(394.3245, t)
    assert p.pruefe(401.0511, t + 300)[0] is None
    assert p.pruefe(401.0512, t + 600)[0] is None
    wert, status = p.pruefe(401.0520, t + 900)
    assert wert == 401.0520 and status.startswith("Neuabgleich")
