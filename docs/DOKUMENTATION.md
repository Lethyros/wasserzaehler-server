# wasserzaehler-server – Nutzer- und Systemdokumentation

## 0 Dokumentinformation

| Feld | Inhalt |
|---|---|
| Titel | wasserzaehler-server – Nutzer- und Systemdokumentation |
| Produktversion | 0.1.0 |
| Dokumentversion | 1.0 |
| Stand | 2026-10-25 |
| Status | freigegeben |
| Autor | Oliver Weber |
| Sprache | Deutsch |
| Gliederung nach | ISO/IEC/IEEE 26514:2022 (Gestaltung und Entwicklung von Nutzerinformation); Inhalte zur Systembeschreibung und Verifikation in Anlehnung an ISO/IEC/IEEE 15289:2019 |
| Lizenz | MIT (Software und Dokumentation) |

### 0.1 Änderungshistorie

| Version | Datum | Änderung |
|---|---|---|
| 1.0 | 2026-10-25 | Erstausgabe |

### 0.2 Konventionen

- `Schreibmaschinenschrift`: Befehle, Dateinamen, Konfigurationsschlüssel.
- **Warnung**: Gefahr von Datenverlust oder falschen Messwerten.
- **Hinweis**: Zusatzinformation.
- Zählerstände in m³, mit Punkt als Dezimaltrennzeichen (`404.7274`).
- „Zeigerwert“ = Stellung eines Zeigers auf der Skala 0,0 … 9,99.

---

## 1 Zweck und Geltungsbereich

`wasserzaehler-server` liest einen mechanischen Wasserzähler mit **Ziffernrollen und roten
Zeigern** zuverlässig aus. Die Fotos liefert eine ESP32-CAM mit der Firmware
[AI-on-the-edge-device](https://github.com/jomjol/AI-on-the-edge-device); die Auswertung läuft
auf einem Linux-Rechner (z. B. LXC-Container, VM, Raspberry Pi) und meldet den Stand per MQTT
an Home Assistant.

Das Projekt löst Probleme, die bei der Auswertung direkt auf dem ESP32 regelmäßig auftreten:

| Problem auf dem ESP32 | Lösung hier |
|---|---|
| Zeiger werden um 180° falsch gelesen (dicker Zeigerkopf wird für die Spitze gehalten) | jeder Zeiger wird **zweifach** gelesen: KI-Modell und rote Zeigerspitze per Bildverarbeitung |
| ein falscher Vorwert blockiert das Gerät dauerhaft („Rate too high“) | Plausibilität mit **Neuabgleich**: nach 3 stimmigen Messungen wird ein neuer Stand übernommen |
| Kamera wandert, Lesebereiche liegen daneben | Ausrichtung mit vielen Bildmerkmalen (ORB) statt zwei Marken |
| keine Aussage, wie sicher ein Wert ist | **Vertrauen 0–100 %** je Messung; unsichere Werte werden nicht veröffentlicht |
| Fehllesungen lassen sich im Nachhinein kaum prüfen | jede Messung wird mit Fotos und Einzelwerten archiviert |

**Nicht im Geltungsbereich:** Zähler ohne Zeiger (nur Rollen), Gas-/Stromzähler mit anderer
Bauform, kommerzielle Nutzung der KI-Modelle (siehe Kapitel 15).

## 2 Begriffe

| Begriff | Bedeutung |
|---|---|
| Rolle | Ziffernrolle des Zählwerks (ganze m³) |
| Zeiger | rotes Zeigerinstrument für die Nachkommastellen (x0,1 / x0,01 / x0,001 / x0,0001 m³) |
| Lesebereich (ROI) | Rechteck im Referenzbild, in dem eine Rolle oder ein Zeiger liegt |
| Referenzbild | gedrehtes Kamerabild, auf das jedes neue Foto ausgerichtet wird |
| Spitze | Bildverarbeitungsverfahren, das die rote Zeigerspitze sucht (`zeiger_cv.py`) |
| KI | TFLite-Klassifikationsmodell aus AI-on-the-edge (class100: 100 Klassen = 0,1er-Schritte) |
| Kette | Prüfung, ob der Nachkommaanteil eines Zeigers zur Stellung des nächstkleineren passt |
| Kettenrest | Abweichung in dieser Prüfung, in Einheiten des nächstkleineren Zeigers |
| Versatz | fester mechanischer Anteil des Kettenrests eines bestimmten Zählers |
| Vertrauen | Gütezahl 0–100 einer Messung (Kapitel 10.6) |
| Neuabgleich | Übernahme eines zunächst unplausiblen Standes nach mehreren stimmigen Messungen |

## 3 Zielgruppe und Voraussetzungen

Zielgruppe: Betreiber eines Smart Homes mit Linux-Grundkenntnissen (SSH, Texteditor, systemd),
die AI-on-the-edge bereits eingerichtet haben.

| Voraussetzung | Mindestens | getestet |
|---|---|---|
| ESP32-CAM mit AI-on-the-edge | v15 (Format der `config.ini`) | v16.1.0, Kamera OV2640 |
| Zähler | Rollen + rote Zeiger | Diehl Corona MW, 4 Rollen + 4 Zeiger |
| Rechner | Linux, Python ≥ 3.11, 1 CPU, 512 MB RAM | Debian 13 (Python 3.13) im LXC, 2 Kerne, 2 GB |
| Speicher | 3 GB für 90 Tage Archiv | 16 GB |
| Netz | Rechner erreicht ESP32 (HTTP) und MQTT-Broker | – |
| MQTT-Broker | beliebig (Mosquitto, HA-Add-on) | Mosquitto |
| KI-Modelle | ein Ziffern- und ein Zeigermodell aus AI-on-the-edge | `dig-class100-0182-s2_q`, `ana-class100_0171_s1_q` |

## 4 Sicherheits- und Datenschutzhinweise

- **Warnung:** Die Webseite (Port 8080) hat **keine Anmeldung**. Über sie kann der Zählerstand
  gesetzt werden. Nur im Heimnetz betreiben, nicht ins Internet freigeben.
- **Warnung:** AI-on-the-edge liefert seine `config.ini` – inklusive MQTT-Passwort – ohne
  Anmeldung unter `http://<esp32>/fileserver/config/config.ini` aus. Für den ESP32 einen
  eigenen MQTT-Benutzer mit minimalen Rechten verwenden oder MQTT dort abschalten (Kapitel 7.4).
- MQTT-Zugangsdaten stehen nie in `config.toml`, sondern in `/etc/wasserzaehler.env`
  (Rechte `600`, gelesen von systemd).
- Das Archiv enthält Fotos des Zählers. Diese zeigen die Zählernummer, die beim Versorger einem
  Haushalt zugeordnet ist. Archiv nicht veröffentlichen.
- Der Dienst läuft als eigener Systembenutzer `wasserzaehler` ohne Login-Shell.

## 5 Systemüberblick

```
 ┌──────────────┐  HTTP /capture_with_flashlight  ┌──────────────────────────────────────────┐
 │  ESP32-CAM   │ ◄────────────────────────────── │ wasserzaehler-server (Python, systemd)   │
 │ AI-on-the-   │ ──── JPEG (640×480, Zoom) ────► │  kamera → ausrichtung → leser            │
 │ edge v16     │                                 │  (KI + Spitze, Kette, Vertrauen)         │
 └──────────────┘                                 │  → Plausibilität → archiv / web / mqtt   │
        ▲  config.ini, reference.jpg, Modelle     └───────────┬───────────────┬──────────────┘
        └──────── einmalig: wasserzaehler uebernehmen         │ MQTT          │ HTTP :8080
                                                              ▼               ▼
                                                     Home Assistant      Browser
```

Module (`wasserzaehler/`):

| Modul | Aufgabe |
|---|---|
| `kamera.py` | Fotos vom ESP32 holen, Drehung wie die Firmware (`InitialRotate`) |
| `ausrichtung.py` | Foto per ORB-Merkmalen auf das Referenzbild ausrichten |
| `erkennung.py` | TFLite-Modelle laden und auswerten (100, 10 oder 2 Ausgänge) |
| `zeiger_cv.py` | Zeigerstellung über die rote Spitze bestimmen |
| `leser.py` | Fotos → Einzelwerte → Zählerstand mit Vertrauen |
| `auswertung.py` | Stellen zusammensetzen (Übertrag), Plausibilität |
| `archiv.py` | Messungen mit Fotos ablegen, aufräumen |
| `mqtt_ha.py` | MQTT inkl. Home-Assistant-Discovery |
| `web.py` | Webseite |
| `einrichtung.py` | Konfiguration von der Kamera übernehmen |
| `konfig.py` | `config.toml` laden |

## 6 Installation

### 6.1 Rechner vorbereiten

Ein Debian/Ubuntu-System (Container, VM oder Pi). Für einen Proxmox-LXC genügen:
unprivilegiert, Debian 13, 2 Kerne, 2 GB RAM, 16 GB Platte, feste IP (oder DHCP-Reservierung).

### 6.2 Programm installieren

Auf dem PC (mit SSH-Zugang als root zum Zielrechner):

```bash
git clone https://github.com/Lethyros/wasserzaehler-server.git
cd wasserzaehler-server
./system/deploy.sh root@<zielrechner>
```

Oder direkt auf dem Zielrechner:

```bash
git clone https://github.com/Lethyros/wasserzaehler-server.git /root/wasserzaehler-quelle
bash /root/wasserzaehler-quelle/system/install.sh
```

`install.sh` erledigt: Pakete (`python3-venv`, `rsync`), Systembenutzer `wasserzaehler`,
Programm nach `/opt/wasserzaehler`, Python-Umgebung mit den Abhängigkeiten aus
`requirements.txt`, Vorlage `/etc/wasserzaehler.env`, systemd-Dienst `wasserzaehler.service`,
Befehl `/usr/local/bin/wasserzaehler`. Ein erneuter Aufruf aktualisiert das Programm und lässt
`config.toml`, `referenz.jpg` und `modelle/` unverändert.

### 6.3 Erfolgskontrolle

```bash
systemctl status wasserzaehler        # nach Kapitel 7: active (running)
wasserzaehler --help
```

## 7 Erstkonfiguration

### 7.1 ESP32 vorbereiten (einmalig, wichtig für die Qualität)

Die Erkennung kann nur so gut sein wie das Foto. In der Weboberfläche von AI-on-the-edge:

1. **Schärfe:** Objektiv der OV2640 vorsichtig nachdrehen (Kleber lösen, in Achtelumdrehungen),
   bis die kleinen Zahlen auf den Zifferblättern klar sind.
2. **Zoom:** `CamZoom = true`, `CamZoomSize` so wählen, dass der Zähler das Bild füllt
   (Beispiel: 14 bei 640×480 und OV2640). Mehr Pixel pro Zeiger = sicherere Erkennung.
3. **Drehung:** `InitialRotate` so, dass die Ziffernrolle waagerecht liegt.
4. **Lesebereiche:** Zeiger-Rechtecke **mittig und quadratisch** über das ganze Zifferblatt,
   Ziffern-Rechtecke auf die Rollenfenster. Reihenfolge der Zeiger: x0,1 zuerst.
5. **Referenzbild** neu aufnehmen (AI-on-the-edge speichert es als `reference.jpg`).
6. Modelle wählen: `dig-class100-*` und `ana-class100-*` (empfohlen).

### 7.2 Konfiguration übernehmen

```bash
wasserzaehler uebernehmen <IP-der-ESP32-CAM>
```

Holt `config.ini`, `reference.jpg` und beide Modelle von der Kamera und schreibt
`/opt/wasserzaehler/config.toml`, `referenz.jpg` und `modelle/`. Bei mehreren Zahlen in der
`config.ini` wählt `--zahl <name>` die richtige; `--ueberschreiben` ersetzt eine vorhandene
Konfiguration.

### 7.3 MQTT eintragen

```bash
nano /opt/wasserzaehler/config.toml        # [mqtt] host = "<broker>"
nano /etc/wasserzaehler.env
#   WASSERZAEHLER_MQTT_BENUTZER=...
#   WASSERZAEHLER_MQTT_PASSWORT=...
systemctl restart wasserzaehler
```

Ohne MQTT (`host = ""`) läuft der Dienst trotzdem, mit Webseite und Archiv.

### 7.4 ESP32 auf „nur Kamera“ umstellen (empfohlen)

Wenn der Server zuverlässig liest, braucht der ESP32 nicht mehr selbst auszuwerten:

- `[AutoTimer] Interval = 1440` – eigener Durchlauf nur noch einmal am Tag
  (abschalten lässt er sich in v16 nicht). Weniger Wärme, keine Konkurrenz um die Kamera.
- `[MQTT]` → `;[MQTT]` – der ESP32 meldet keine eigenen (womöglich falschen) Werte mehr.

`/capture_with_flashlight` funktioniert unabhängig davon weiter.

### 7.5 Erster Stand

Die erste Messung wird ohne Plausibilitätsprüfung übernommen. Danach mit dem Zähler
vergleichen; bei Bedarf auf der Webseite oder per MQTT korrigieren (Kapitel 8.4).

## 8 Betrieb

### 8.1 Ablauf

Der Dienst misst alle `intervall_s` Sekunden (Standard 300) und zusätzlich auf Anforderung
(Webseite, MQTT-Knopf). Eine Messung dauert mit 3 Fotos etwa 10–12 s.

### 8.2 Webseite (`http://<rechner>:8080`)

| Adresse | Inhalt |
|---|---|
| `/` | Stand, Vertrauen, Status, Gründe, ESP32-Vergleichswert, markiertes Bild, letzte 40 Messungen |
| `/messung/<tag>/<zeit>` | eine Messung: alle Fotos und das vollständige Ergebnis (JSON) |
| `/zustand.json` | aktueller Zustand maschinenlesbar |
| `/bild/aktuell.jpg` | ausgerichtetes Bild mit Lesebereichen und erkannten Werten |
| `/bild/roh.jpg`, `/bild/referenz.jpg` | letztes Rohfoto, Referenzbild |
| `POST /messen` | sofort messen |
| `POST /setzen` (Feld `wert`) | Zählerstand von Hand setzen |

![Ausgerichtetes Bild mit erkannten Werten](bilder/erkennung.jpg)

Farben im Bild: blau = Rollen, grün = Zeiger, orange = Stelle mit Hinweis (z. B. KI und Spitze uneinig).

### 8.3 MQTT und Home Assistant

Themen (Basis `basis`, Standard `wasserzaehler`):

| Thema | Richtung | Inhalt | retained |
|---|---|---|---|
| `<basis>/verfuegbar` | aus | `online` / `offline` (Last Will) | ja |
| `<basis>/zaehlerstand` | aus | Stand in m³, 4 Nachkommastellen; beim Start Vorwert | ja |
| `<basis>/zustand` | aus | JSON: `zaehlerstand`, `gelesen`, `roh`, `vertrauen`, `status`, `gruende`, `durchfluss_l_min`, `esp32`, `zeit`, `dauer_s`, `verschiebung`, `archiv` | ja |
| `<basis>/bild` | aus | JPEG mit Lesebereichen | ja |
| `<basis>/lesen/set` | ein | beliebig → sofort messen | – |
| `<basis>/zaehlerstand/setzen` | ein | Stand in m³ (Komma oder Punkt) | – |
| `vergleich_topic` | ein | optional: Wert des ESP32, nur zur Anzeige | – |

Per Discovery (`discovery_praefix`) legt Home Assistant das Gerät **„Wasserzähler (Server)“** an:

| Entität | Typ | Hinweis |
|---|---|---|
| Zählerstand | sensor, `device_class: water`, `state_class: total_increasing` | für das Energie-Dashboard (Wasser) |
| Durchfluss | sensor, L/min | seit der letzten veröffentlichten Messung |
| Vertrauen | sensor, % | Diagnose |
| Status, Rohwert | sensor | Diagnose; Status trägt den ganzen Zustand als Attribute |
| Kamerabild | image | |
| Jetzt messen | button | |
| Zählerstand setzen | number | Konfiguration |

**Hinweis:** Es wird nur veröffentlicht, wenn das Vertrauen mindestens `mindestvertrauen`
beträgt und die Plausibilität passt. Sonst bleibt der letzte Stand stehen und `status` nennt den Grund.

### 8.4 Zählerstand setzen

Nötig nach Zählertausch oder wenn der erste Wert falsch war. Webseite (Formular) oder MQTT
`<basis>/zaehlerstand/setzen`. Der neue Stand gilt sofort als Vorwert. Bei falschem Vorwert ist
das nicht zwingend nötig: nach `neuabgleich_nach` stimmigen Messungen gleicht der Dienst selbst ab.

### 8.5 Archiv

`/var/lib/wasserzaehler/archiv/<JJJJ-MM-TT>/<HHMMSS>Z/` (Zeit in UTC):
`foto1.jpg` … (Originalfotos der Kamera, ungedreht) und `ergebnis.json` (Anhang C).
Einträge älter als `archiv.tage` werden einmal täglich gelöscht. Platzbedarf ≈ 25–35 MB/Tag
bei 3 Fotos alle 5 Minuten.

### 8.6 Kalibrieren

Die Zeiger eines Zählers stehen mechanisch nicht exakt zueinander. Nach einigen Tagen mit
Wasserverbrauch:

```bash
wasserzaehler kalibrieren
```

Ausgabe: Vorschlag für `[zaehler.ketten_versatz]` je Zeiger mit Streuung und der Zahl gesehener
Zeigerstellungen. Werte übernehmen, wenn möglichst viele der 10 Stellungen gesehen wurden,
dann `systemctl restart wasserzaehler`. Ein falscher Versatz kostet nur Vertrauen, ändert aber
keinen Wert, solange KI und Spitze übereinstimmen.

### 8.7 Bilder offline prüfen

```bash
wasserzaehler lies foto1.jpg foto2.jpg foto3.jpg
```

Liest Rohfotos (z. B. aus dem Archiv) als eine Messung, zeigt jede Stelle mit KI- und
Spitzenwert und legt `foto1_gelesen.jpg` mit eingezeichneten Werten ab.

## 9 Konfigurationsreferenz (`config.toml`)

Relative Pfade gelten relativ zum Ordner der `config.toml`.

### `[kamera]`
| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `host` | `192.168.0.13` | IP/Name der ESP32-CAM |
| `drehung_grad` | `0` | = `InitialRotate` der Kamera |
| `pause_zwischen_fotos_s` | `1.0` | Pause zwischen den Fotos einer Messung |
| `versuche` | `4` | Wiederholungen, wenn die Kamera beschäftigt ist |

### `[zaehler]`
| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `referenzbild` | – | gedrehtes Referenzbild (von der Kamera) |
| `modell_ziffern`, `modell_zeiger` | – | TFLite-Modelle |
| `ziffern` | – | Liste `{ name, rechteck = [x, y, b, h] }`, höchste Stelle zuerst |
| `zeiger` | – | Liste wie oben, x0,1 zuerst |
| `ziffer_mindestsicherheit` | `0.0` | darunter gilt eine Rolle als unlesbar |
| `max_abweichung_methoden` | `1.0` | bis zu diesem Abstand werden KI und Spitze gemittelt |
| `max_kettenrest` | `2.5` | größerer Kettenrest (nach Versatz) kostet Vertrauen |
| `[zaehler.ketten_versatz]` | leer | `"<zeigername>" = <wert>`, siehe 8.6 |

### `[messung]`
| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `intervall_s` | `300` | Abstand der Messungen |
| `bilder_pro_messung` | `3` | Fotos je Messung (ungerade Zahl empfohlen) |
| `max_durchfluss_m3h` | `5.0` | größter plausibler Durchfluss (Q4 des Zählers) |
| `neuabgleich_nach` | `3` | so viele stimmige Messungen übernehmen einen unplausiblen Stand |
| `mindestvertrauen` | `50` | darunter wird nicht veröffentlicht |

### `[archiv]`
| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `pfad` | `/var/lib/wasserzaehler/archiv` | Ablage der Messungen |
| `tage` | `90` | Aufbewahrung |
| `zustandsdatei` | `/var/lib/wasserzaehler/zustand.json` | letzter Stand über Neustarts |

### `[mqtt]`
| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `host` | – | Broker; leer = kein MQTT |
| `port` | `1883` | |
| `basis` | `wasserzaehler` | Themen-Präfix und Discovery-ID |
| `client_id` | `wasserzaehler-server` | |
| `discovery_praefix` | `homeassistant` | |
| `vergleich_topic` | leer | Thema mit dem Wert des ESP32 zur Anzeige |
| Zugangsdaten | – | `WASSERZAEHLER_MQTT_BENUTZER`, `WASSERZAEHLER_MQTT_PASSWORT` in `/etc/wasserzaehler.env` |

### `[web]`
| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `port` | `8080` | Webseite |

## 10 Funktionsweise

### 10.1 Foto und Drehung
Je Messung `bilder_pro_messung` Aufrufe von `/capture_with_flashlight` (frisches Bild mit LED,
Zoom laut Kamera-Konfiguration). Jedes Foto wird wie in der Firmware (`CRotateImage::Rotate`)
um die Bildmitte gedreht; die Lesebereiche der Kamera gelten dadurch unverändert.

### 10.2 Ausrichtung
ORB-Merkmale (3000) von Foto und Referenzbild, Kontrastausgleich (CLAHE), Abgleich mit
Verhältnistest 0,75, Ähnlichkeitstransformation per RANSAC. Abgelehnt wird bei weniger als
25 übereinstimmenden Merkmalen oder Maßstab außerhalb 0,7–1,4. Die Verschiebung je Foto steht
in `zustand.verschiebung` – wächst sie über Tage, wandert die Kamera.

### 10.3 Rollen
Ziffernmodell auf jedem Rollen-Lesebereich. class100: Klasse k → k/10 (z. B. 4.7 = Rolle zu 70 %
von 4 auf 5 gedreht).

### 10.4 Zeiger: KI und Spitze
- **KI:** Zeigermodell (class100) → 0,0 … 9,9.
- **Spitze:** roter Anteil über den a*-Kanal (Lab). Schwelle = Hintergrund + 45 % des Abstands
  zum rötesten Pixel (unempfindlich gegen Belichtung und Weißabgleich). Bereich außerhalb von
  85 % des Radius wird ignoriert, es zählt nur das rote Teil an der Mitte. Die **Achse** ist die
  dickste Stelle des Zeigers (Maximum der Distanztransformation = Mitte des runden Kopfs), sofern
  sie nahe der Bildmitte liegt. Die Spitze sind die Pixel ab 80 % des größten Achsabstands; ihre
  abstandsgewichtete Richtung ergibt den Winkel, 0° = oben, im Uhrzeigersinn, 36° je Einheit.
  Ergebnisse mit Sicherheit < 0,3 werden verworfen.
- **Zusammenführen** (von der kleinsten Stelle zur größten):

| Fall | Ergebnis |
|---|---|
| Abstand KI ↔ Spitze ≤ 0,3 | Spitze (feinere Auflösung) |
| Abstand ≤ `max_abweichung_methoden` | Kreismittel beider |
| größerer Abstand | der Wert mit dem kleineren Kettenrest zum (bereits bestimmten) Nachfolger; beim kleinsten Zeiger die Spitze; Hinweis „uneinig“ |
| nur ein Verfahren liefert | dieses; Hinweis „nur KI/Spitze“ |

### 10.5 Zusammensetzen und Übertrag
Für jede Stelle (Zeiger und Rollen) wird die ganze Zahl k gewählt, die am besten zum
gleitenden Wert der rechten Nachbarstelle passt: Steht die Nachbarin bei p, muss der
Nachkommaanteil zwischen max(0, p−9) (Rolle springt erst am Ende) und p/10 (läuft gleichmäßig
mit) liegen. Eine Rolle, die ihrer Nachbarin mechanisch „voraus“ wäre, wird doppelt bestraft.
So werden halb gedrehte Rollen richtig zugeordnet, unabhängig von der Mechanik des Zählers.

### 10.6 Mehrere Fotos und Vertrauen
Jedes Foto wird vollständig ausgewertet; der **Median der Fotowerte** ist das Ergebnis (Fotos
können während des Wasserlaufs verschiedene Zeigerstellungen zeigen – Stellen über Fotos zu
mitteln würde Zeitpunkte mischen). Vertrauen = 100 abzüglich:

| Befund | Abzug |
|---|---|
| Zeiger unlesbar | 60 |
| KI und Spitze uneinig (Kette entschied) | 25 |
| nur ein Verfahren lieferte | 15 |
| Kettenrest − Versatz > `max_kettenrest` (je Zeigerpaar) | 20 |
| Rolle unlesbar | 30 (ohne Vorwert: kein Ergebnis) |
| höchstens die Hälfte der Fotos lesbar | 30 |
| Fotowerte weichen > 0,01 m³ vom Median ab | 30 |

Fotos, die sich nicht ausrichten lassen, werden genannt, kosten aber kein Vertrauen, solange die
Mehrheit lesbar ist.

### 10.7 Plausibilität
Nach dem Vertrauen (`mindestvertrauen`) prüft der Dienst gegen den letzten veröffentlichten Stand:

| Fall | Ergebnis |
|---|---|
| kein Vorwert | übernommen („erster Wert“) |
| 0 ≤ Zuwachs ≤ `max_durchfluss_m3h` × Stunden + 0,002 (mind. 1 Minute) | übernommen |
| Rückgang ≤ 0,0005 m³ | ignoriert, alter Stand bleibt („Rauschen rückwärts“) |
| sonst | verworfen; liefern `neuabgleich_nach` Messungen untereinander stimmige Werte, wird übernommen („Neuabgleich“) |

Vorwert beim Start: `zustandsdatei`, sonst der retained MQTT-Wert.

## 11 Fehlersuche

| Symptom | Ursache | Abhilfe |
|---|---|---|
| `Kamera … nicht erreichbar` | ESP32 aus, falsche IP, ESP32 gerade im eigenen Durchlauf | IP prüfen; `[AutoTimer] Interval` erhöhen (7.4) |
| `Ausrichtung fehlgeschlagen: zu wenig passende Merkmale` | Kamera stark verschoben/verdreht, Bild dunkel, Referenzbild veraltet | Referenzbild und Lesebereiche in AI-on-the-edge neu setzen, `uebernehmen --ueberschreiben` |
| Vertrauen dauerhaft 80 mit „passt nicht zusammen“ | fester Versatz der Zeiger | `wasserzaehler kalibrieren` (8.6) |
| „KI … / Spitze … uneinig“ gehäuft | Lesebereich nicht mittig, Spiegelung auf dem Zeiger | Lesebereich mittig setzen, LED-Helligkeit senken, Diffusor |
| `unsicher (… %)` | mehrere Befunde aus 10.6 | Messung auf der Webseite öffnen, Fotos ansehen |
| `verworfen: Sprung` | Fehllesung oder echter Sprung (Zählertausch) | wartet auf Neuabgleich; bei Zählertausch Stand setzen (8.4) |
| `verworfen: rückwärts` | falscher, zu hoher Vorwert | nach 3 stimmigen Messungen Neuabgleich; oder Stand setzen |
| Entitäten fehlen in HA | MQTT-Integration/Discovery aus, falscher Präfix | `discovery_praefix`, Broker-Zugang, `journalctl -u wasserzaehler` |
| `Modell mit … Ausgängen wird nicht unterstützt` | Modelltyp unbekannt | class100-Modelle verwenden (100 Ausgänge) |

Protokoll: `journalctl -u wasserzaehler -f`.

## 12 Verifikation

### 12.1 Automatische Tests (`pytest`)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
# Modelle nach modelle/ legen (z. B. wasserzaehler uebernehmen <IP> --ziel .)
.venv/bin/python -m pytest -q tests
```

| Testgruppe | Prüft |
|---|---|
| `test_auswertung.py` (10) | Übertrag, halb gedrehte Rollen, Umlauf 9→0, Plausibilität, Neuabgleich |
| `test_einrichtung.py` (2) | Einlesen der `config.ini` von AI-on-the-edge |
| `test_leser.py` (17) | Kreisrechnung; 3 Einzelfotos und eine Dreiermessung (404,7274 m³, Vertrauen 100); Spitze auf allen Zeigern; **simulierter 180°-Fehler der KI** wird erkannt und korrigiert; **10 Messungen aus dem Betrieb** (404,7274 … 404,8008 m³), davon eine bei laufendem Wasser |

Ohne Modelle werden die bildbasierten Tests übersprungen.

### 12.2 Feldtest (24./25.10.2026, Diehl Corona MW, AI-on-the-edge v16.1.0)

| Kennzahl | Ergebnis |
|---|---|
| Messungen | 111 in 8,5 h, alle 5 min |
| veröffentlichte Fehlwerte | 0 (kein Sprung, kein Rückschritt) |
| Vertrauen | 105 × 100 %, 6 × 80–85 %, 0 × < 80 % (nach Verbesserung aus 12.3: 10/10 Stichproben 100 %) |
| Abgleich mit den Rohwerten des ESP32 | 83 von 91 auf ±0,0005 m³ gleich; Rest durch Zeitversatz bei laufendem Wasser |
| vom Doppelverfahren abgefangen | KI las x0,1 einmal mit 1,5 statt 7,2 (180°-Fehler) – veröffentlichter Wert korrekt |
| Messdauer | 10–12 s für 3 Fotos |

### 12.3 Aus dem Feldtest abgeleitete Änderungen
- Achse aus der Kopfmitte statt Bildmitte: Kettenrest x0,01→x0,001 schwankte vorher je nach
  Stellung von −3,1 bis +0,6, danach −1,9 bis −0,1.
- Auswertung je Foto, dann Median: Messungen bei laufendem Wasser ohne Vertrauensverlust.
- Archivordner in UTC: bei der Zeitumstellung gab es die Stunde 2–3 Uhr doppelt.

## 13 Bekannte Einschränkungen

- Nur Zähler mit Rollen **und** roten Zeigern; Zeiger anderer Farbe erkennt das Spitzenverfahren nicht (die KI liest dann allein, Vertrauen −15 je Zeiger).
- Die vorderste Rolle muss nicht konfiguriert sein, wenn sie dauerhaft 0 zeigt; fehlt sie, fehlt sie im Wert.
- Der Versatz wird als konstant angenommen; ein stellungsabhängiger Rest bleibt (siehe 12.3) und wird über `max_kettenrest` toleriert.
- Der ESP32 bleibt nötig (Kamera + LED). Fällt der Rechner aus, gibt es keine Werte; nach dem Neustart wird sofort wieder der absolute Stand gelesen.
- Webseite ohne Anmeldung (Kapitel 4).

## 14 Wartung

| Aufgabe | Vorgehen |
|---|---|
| Aktualisieren | `git pull`, dann `./system/deploy.sh root@<rechner>` bzw. `install.sh` erneut |
| Kamera verstellt | in AI-on-the-edge Referenzbild/Lesebereiche neu, dann `wasserzaehler uebernehmen <IP> --ueberschreiben`, MQTT-Werte wieder eintragen |
| Versatz nachziehen | `wasserzaehler kalibrieren` (8.6) |
| Sicherung | `/opt/wasserzaehler/config.toml`, `referenz.jpg`, `/etc/wasserzaehler.env`, optional `/var/lib/wasserzaehler` |
| Deinstallieren | `systemctl disable --now wasserzaehler`; `rm -r /opt/wasserzaehler /var/lib/wasserzaehler /etc/wasserzaehler.env /etc/systemd/system/wasserzaehler.service /usr/local/bin/wasserzaehler`; `userdel wasserzaehler`; in HA das Gerät löschen bzw. retained Discovery-Themen leeren |

## 15 Lizenz und Fremdkomponenten

Dieses Projekt steht unter der MIT-Lizenz (`LICENSE`). Die KI-Modelle gehören zu
AI-on-the-edge-device und stehen unter dessen Dual-Use-Lizenz (privat frei, kommerziell nur mit
Lizenz des Rechteinhabers); sie sind deshalb nicht enthalten. Details: `DRITTANBIETER.md`.

---

## Anhang A – Befehle

| Befehl | Wirkung |
|---|---|
| `wasserzaehler uebernehmen HOST [--zahl N] [--ziel DIR] [--ueberschreiben]` | Konfiguration, Referenzbild, Modelle von der Kamera |
| `wasserzaehler dienst` | Dauerbetrieb (vom systemd-Dienst aufgerufen) |
| `wasserzaehler lies BILD…` | Rohfotos als eine Messung auswerten |
| `wasserzaehler kalibrieren` | Versatz aus dem Archiv vorschlagen |
| `wasserzaehler foto [-o DATEI]` | ein gedrehtes Foto speichern |
| Option `-c DATEI` | andere `config.toml` (Standard `/opt/wasserzaehler/config.toml`) |
| Option `-v` | ausführliches Protokoll |

## Anhang B – Dateien

| Pfad | Inhalt |
|---|---|
| `/opt/wasserzaehler/` | Programm, `config.toml`, `referenz.jpg`, `modelle/`, `venv/` |
| `/etc/wasserzaehler.env` | MQTT-Zugangsdaten (600) |
| `/etc/systemd/system/wasserzaehler.service` | Dienst |
| `/var/lib/wasserzaehler/zustand.json` | letzter Stand und Zeitpunkt |
| `/var/lib/wasserzaehler/archiv/` | Messungen |

## Anhang C – `ergebnis.json`

```json
{
 "wert": 404.7807, "roh": "0404.7807", "vertrauen": 100, "gruende": [],
 "ziffern": [{"name": "dig1", "wert": 4.7, "ki": [4.7, 4.7, 4.7], "spitze": []}],
 "zeiger": [{"name": "ana1", "wert": 7.88, "ki": [7.8, 7.8, 7.8], "spitze": [7.88, 7.86, 7.88],
             "hinweis": "(nur bei Auffälligkeiten)"}],
 "ausrichtung": [{"treffer": 1720, "winkel": -0.02, "massstab": 1.002, "verschiebung": [-1.1, -6.6]}],
 "zeit": "2026-10-25T07:49:25+01:00", "status": "ok", "veroeffentlicht": 404.7807, "esp32": null
}
```

(`ziffern`/`zeiger` gekürzt; `wert` je Stelle stammt vom Median-Foto, `ki`/`spitze` enthalten die
Werte aller Fotos.)
