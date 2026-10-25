"""MQTT mit Home-Assistant-Discovery.

Themen (Basis z. B. "wasserzaehler"):
  <basis>/verfuegbar          online/offline (Last Will)
  <basis>/zaehlerstand        m³, retained – dient beim Start auch als Vorwert
  <basis>/zustand             JSON: roh, status, vertrauen, durchfluss, gründe …
  <basis>/bild                JPEG des ausgerichteten Bildes mit Lesebereichen
  <basis>/lesen/set           sofort messen
  <basis>/zaehlerstand/setzen Zählerstand von Hand korrigieren
Zum Vergleich wird der Wert des ESP32 mitgelesen (vergleich_topic).
"""

import json
import logging
import threading

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


class HaMqtt:
    def __init__(self, cfg: dict, version: str):
        self.basis = cfg.get("basis", "wasserzaehler")
        self.ha_praefix = cfg.get("discovery_praefix", "homeassistant")
        self.vergleich_topic = cfg.get("vergleich_topic", "")
        self.version = version
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg.get("client_id", "wasserzaehler-server"))
        if cfg.get("benutzer"):
            self.c.username_pw_set(cfg["benutzer"], cfg.get("passwort", ""))
        self.c.will_set(f"{self.basis}/verfuegbar", "offline", retain=True)
        self.c.on_connect = self._verbunden
        self.c.on_message = self._nachricht
        self.host, self.port = cfg.get("host", "192.168.0.50"), int(cfg.get("port", 1883))
        self.vorwert: float | None = None
        self.vorwert_da = threading.Event()
        self.esp32_wert: str | None = None
        # Rückrufe, werden vom Hauptprogramm gesetzt
        self.bei_lesen = lambda: None
        self.bei_setzen = lambda wert: None

    def starten(self):
        self.c.connect_async(self.host, self.port, keepalive=60)
        self.c.loop_start()

    def warte_auf_vorwert(self, sekunden=8.0) -> float | None:
        self.vorwert_da.wait(sekunden)
        return self.vorwert

    def _verbunden(self, client, userdata, flags, rc, *args):
        log.info("MQTT verbunden (%s)", rc)
        b = self.basis
        themen = [(f"{b}/zaehlerstand", 1), (f"{b}/lesen/set", 1), (f"{b}/zaehlerstand/setzen", 1)]
        if self.vergleich_topic:
            themen.append((self.vergleich_topic, 0))
        client.subscribe(themen)
        self._discovery()
        client.publish(f"{b}/verfuegbar", "online", retain=True)

    def _nachricht(self, client, userdata, msg):
        b, text = self.basis, msg.payload.decode(errors="replace").strip()
        try:
            if msg.topic == f"{b}/zaehlerstand":
                if not self.vorwert_da.is_set():  # nur einmal beim Start (retained)
                    self.vorwert = float(text) if text else None
                    self.vorwert_da.set()
            elif msg.topic == f"{b}/lesen/set":
                self.bei_lesen()
            elif msg.topic == f"{b}/zaehlerstand/setzen":
                self.bei_setzen(float(text.replace(",", ".")))
            elif msg.topic == self.vergleich_topic:
                self.esp32_wert = text
        except Exception:
            log.exception("MQTT-Nachricht %s nicht verarbeitet: %r", msg.topic, text)

    def _discovery(self):
        b, p = self.basis, self.ha_praefix
        geraet = {"identifiers": [b], "name": "Wasserzähler (Server)", "manufacturer": "Eigenbau",
                  "model": "ESP32-CAM + Auswertung im LXC", "sw_version": self.version}
        gemein = {"availability_topic": f"{b}/verfuegbar", "device": geraet}
        eintraege = {
            ("sensor", "zaehlerstand"): {"name": "Zählerstand", "state_topic": f"{b}/zaehlerstand",
                                         "unit_of_measurement": "m³", "device_class": "water",
                                         "state_class": "total_increasing", "suggested_display_precision": 4,
                                         "icon": "mdi:water"},
            ("sensor", "durchfluss"): {"name": "Durchfluss", "state_topic": f"{b}/zustand",
                                       "value_template": "{{ value_json.durchfluss_l_min }}",
                                       "unit_of_measurement": "L/min", "device_class": "volume_flow_rate",
                                       "state_class": "measurement"},
            ("sensor", "vertrauen"): {"name": "Vertrauen", "state_topic": f"{b}/zustand",
                                      "value_template": "{{ value_json.vertrauen }}", "unit_of_measurement": "%",
                                      "state_class": "measurement", "icon": "mdi:check-decagram",
                                      "entity_category": "diagnostic"},
            ("sensor", "status"): {"name": "Status", "state_topic": f"{b}/zustand",
                                   "value_template": "{{ value_json.status }}", "icon": "mdi:information-outline",
                                   "json_attributes_topic": f"{b}/zustand", "entity_category": "diagnostic"},
            ("sensor", "rohwert"): {"name": "Rohwert", "state_topic": f"{b}/zustand",
                                    "value_template": "{{ value_json.roh }}", "icon": "mdi:counter",
                                    "entity_category": "diagnostic"},
            ("image", "bild"): {"name": "Kamerabild", "image_topic": f"{b}/bild", "content_type": "image/jpeg"},
            ("button", "lesen"): {"name": "Jetzt messen", "command_topic": f"{b}/lesen/set",
                                  "icon": "mdi:camera-iris"},
            ("number", "setzen"): {"name": "Zählerstand setzen", "command_topic": f"{b}/zaehlerstand/setzen",
                                   "state_topic": f"{b}/zaehlerstand", "min": 0, "max": 99999, "step": 0.0001,
                                   "mode": "box", "unit_of_measurement": "m³", "entity_category": "config"},
        }
        for (art, obj), conf in eintraege.items():
            conf = {**gemein, **conf, "unique_id": f"{b}_{obj}"}
            self.c.publish(f"{p}/{art}/{b}/{obj}/config", json.dumps(conf, ensure_ascii=False), retain=True)

    def zaehlerstand(self, wert: float):
        self.c.publish(f"{self.basis}/zaehlerstand", f"{wert:.4f}", retain=True)

    def zustand(self, daten: dict):
        self.c.publish(f"{self.basis}/zustand", json.dumps(daten, ensure_ascii=False), retain=True)

    def bild(self, jpeg: bytes):
        self.c.publish(f"{self.basis}/bild", jpeg, retain=True)

    def beenden(self):
        self.c.publish(f"{self.basis}/verfuegbar", "offline", retain=True).wait_for_publish(3)
        self.c.loop_stop()
        self.c.disconnect()
