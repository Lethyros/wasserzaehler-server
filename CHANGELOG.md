# Änderungen

## 0.2.0 – 2026-10-26

Beschlagenes Sichtfenster. In der Nacht zum 26.10. beschlug das Glas nach Wasserentnahme
stundenlang; das Ziffernmodell las die Rollen als „0000“/„0005“, und Version 0.1.0 glich den
Stand nach drei stimmigen Fehllesungen auf 0,5 bzw. 5,5 m³ ab.

- Kontrast jeder Rolle wird mit dem Referenzbild verglichen (`rollen_mindestkontrast`, 0.6);
  bei beschlagenem Glas kommen die ganzen m³ aus dem letzten Stand, gelesen werden nur die Zeiger
- Neuabgleich zählt nur Messungen mit klaren Rollen und Vertrauen ≥ `neuabgleich_vertrauen` (90)
- `neuabgleich_nach` 3 → 6
- `ergebnis.json` und MQTT-Zustand: `rollen_klar`, `rollen_kontrast`
- Tests mit zwei beschlagenen Messungen aus dem Betrieb

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
