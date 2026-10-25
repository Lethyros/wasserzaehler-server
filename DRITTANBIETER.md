# Fremdkomponenten

| Komponente | Verwendung | Lizenz | Im Repository? |
|---|---|---|---|
| [AI-on-the-edge-device](https://github.com/jomjol/AI-on-the-edge-device) (Firmware der ESP32-CAM) | liefert die Fotos, Lesebereiche, Referenzbild | Dual Use License (privat frei, kommerziell nur mit Lizenz) | nein – läuft auf der Kamera |
| TFLite-Modelle aus AI-on-the-edge (`dig-class100-*`, `ana-class100-*`) | Ziffern- und Zeigererkennung | wie AI-on-the-edge | **nein** – werden mit `wasserzaehler uebernehmen` von der eigenen Kamera geholt |
| OpenCV (`opencv-python-headless`) | Bildverarbeitung | Apache-2.0 | nein (pip) |
| NumPy | Rechnen | BSD-3-Clause | nein (pip) |
| Eclipse Paho MQTT (`paho-mqtt`) | MQTT | EPL-2.0 / EDL-1.0 | nein (pip) |
| LiteRT (`ai-edge-litert`) | TFLite-Laufzeit | Apache-2.0 | nein (pip) |

`kamera.drehen_wie_firmware` rechnet die Drehung von AI-on-the-edge (`CRotateImage::Rotate`)
mathematisch nach, damit die Lesebereiche aus der Kamera-Konfiguration passen; Code der
Firmware ist nicht enthalten.

Die Testbilder in `tests/testdaten/` stammen von einem Diehl Corona MW des Autors; die
Seriennummer des Zählers ist unkenntlich gemacht.
