# Änderungen

## 0.1.0 – 2026-10-25

Erste Veröffentlichung.

- Fotos von der ESP32-CAM (AI-on-the-edge, `/capture_with_flashlight`), Drehung wie die Firmware
- Ausrichtung per ORB-Merkmalen
- Rollen und Zeiger mit den class100-Modellen, Zeiger zusätzlich über die rote Spitze
  (Achse aus der Mitte des Zeigerkopfs)
- Zusammensetzen mit Übertragslogik, Kettenprüfung der Zeiger mit lernbarem Versatz
- je Foto vollständige Auswertung, Median, Vertrauen 0–100
- Plausibilität mit Neuabgleich, Zustand über Neustarts
- MQTT mit Home-Assistant-Discovery, Webseite, Archiv mit Aufräumen
- Befehle `uebernehmen`, `lies`, `kalibrieren`, `foto`
- Installation als systemd-Dienst (`system/install.sh`, `system/deploy.sh`)
