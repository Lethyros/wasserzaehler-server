from wasserzaehler.einrichtung import lies_config_ini

# gekürzte config.ini von AI-on-the-edge v16 (Zugangsdaten entfernt)
INI = """[TakeImage]
CamZoom = true

[Alignment]
InitialRotate = 47.75
SearchFieldX = 20
AlignmentAlgo = Default
/config/ref0.jpg 230 80
/config/ref1.jpg 305 415

[Digits]
Model = /config/dig-class100-0182-s2_q.tflite
CNNGoodThreshold = 0.5
;ROIImagesLocation = /log/digit
main.dig1000 287 127 26 42 0
main.dig100 319 127 26 42 0
main.dig10 351 127 26 42 0
main.dig1 380 127 26 42 0

[Analog]
Model = /config/ana-class100_0171_s1_q.tflite
main.ana1 388 230 96 96 false
main.ana2 336 322 96 96 false
gas.ana1 10 10 50 50 false

;[MQTT]
Uri = mqtt://example.invalid:1883
main.DomoticzIDX = 1 2 3 4
"""


def test_config_ini_lesen():
    d = lies_config_ini(INI)
    assert d["drehung"] == 47.75
    assert d["zahl"] == "main"
    assert d["modell_ziffern"] == "/config/dig-class100-0182-s2_q.tflite"
    assert d["ziffern"][0] == ("dig1000", 287, 127, 26, 42)
    assert [z[0] for z in d["zeiger"]] == ["ana1", "ana2"]


def test_andere_zahl_waehlen():
    d = lies_config_ini(INI, "gas")
    assert d["zeiger"] == [("ana1", 10, 10, 50, 50)] and d["ziffern"] == []
