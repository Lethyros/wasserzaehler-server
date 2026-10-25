"""Kleine Webseite (Port 8080): Stand, Vertrauen, letzte Messungen mit Fotos.

Kein Login – nur im Heimnetz betreiben.
"""

import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

KOPF = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{titel}</title>
<style>
:root{{--bg:#111;--fg:#ddd;--dim:#888;--rand:#333;--gut:#4c6;--mittel:#db3;--schlecht:#e55;--link:#6af}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg);margin:0 auto;padding:16px;max-width:1000px}}
a{{color:var(--link)}} img{{max-width:100%;border:1px solid var(--rand)}}
.w{{font-size:40px;font-weight:600}} .dim{{color:var(--dim)}}
table{{border-collapse:collapse;width:100%;font-size:14px}} td,th{{padding:4px 8px;border-bottom:1px solid var(--rand);text-align:left}}
.v{{display:inline-block;min-width:3em;text-align:right}} .g{{color:var(--gut)}} .m{{color:var(--mittel)}} .s{{color:var(--schlecht)}}
button,input{{font-size:15px;padding:5px 10px}} form{{display:inline-block;margin:6px 12px 6px 0}}
.fotos{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}}
pre{{background:#000;padding:8px;overflow:auto;font-size:12px}}
</style></head><body>"""


def _klasse(v):
    return "dim" if v is None else "g" if v >= 80 else "m" if v >= 50 else "s"


def _e(x):
    return html.escape("" if x is None else str(x))


class Web:
    def __init__(self, cfg: dict, dienst):
        self.port = int(cfg.get("port", 8080))
        d = dienst

        def startseite():
            z = dict(d.zustand)
            wert = z.get("zaehlerstand")
            v = z.get("vertrauen")
            zeilen = []
            for m in d.archiv.letzte(40):
                mv = m.get("vertrauen")
                zeilen.append(
                    f"<tr><td><a href='/messung/{_e(m['ordner'])}'>{_e(m.get('zeit', '')[5:19].replace('T', ' '))}</a></td>"
                    f"<td>{_e(m.get('wert'))}</td><td><span class='v {_klasse(mv)}'>{_e(mv)} %</span></td>"
                    f"<td>{_e(m.get('veroeffentlicht'))}</td><td class='dim'>{_e(m.get('esp32'))}</td>"
                    f"<td class='dim'>{_e(m.get('status'))}</td></tr>")
            gruende = "".join(f"<li>{_e(g)}</li>" for g in z.get("gruende") or [])
            return (KOPF.format(titel="Wasserzähler") +
                    f"<h1>Wasserzähler</h1><div class='w'>{'–' if wert is None else f'{wert:.4f}'} m³</div>"
                    f"<p>Vertrauen <span class='{_klasse(v)}'>{_e(v)} %</span> · {_e(z.get('status'))} · "
                    f"<span class='dim'>{_e(z.get('zeit'))}</span><br>"
                    f"<span class='dim'>ESP32 meldet: {_e(z.get('esp32'))} · Durchfluss {_e(z.get('durchfluss_l_min'))} L/min"
                    f" · Messdauer {_e(z.get('dauer_s'))} s</span></p>"
                    f"{'<ul>' + gruende + '</ul>' if gruende else ''}"
                    "<form method='post' action='/messen'><button>Jetzt messen</button></form>"
                    "<form method='post' action='/setzen'><input name='wert' size='10' placeholder='404.7274'>"
                    "<button>Zählerstand setzen</button></form> <a href='/zustand.json'>zustand.json</a>"
                    "<h3>Letzte Messung</h3><img src='/bild/aktuell.jpg?" + _e(z.get("zeit")) + "'>"
                    "<h3>Verlauf</h3><table><tr><th>Zeit</th><th>gelesen</th><th>Vertrauen</th>"
                    "<th>veröffentlicht</th><th>ESP32</th><th>Status</th></tr>" + "".join(zeilen) +
                    "</table></body></html>")

        def messung(ordner):
            p = d.archiv.datei(ordner + "/ergebnis.json")
            if not p:
                return None
            e = json.loads(p.read_text())
            fotos = sorted(p.parent.glob("foto*.jpg"))
            return (KOPF.format(titel=f"Messung {ordner}") +
                    f"<p><a href='/'>← zurück</a></p><h2>{_e(e.get('zeit'))}</h2>"
                    f"<div class='w'>{_e(e.get('wert'))}</div><p>Vertrauen {_e(e.get('vertrauen'))} % · "
                    f"{_e(e.get('status'))}</p><div class='fotos'>" +
                    "".join(f"<a href='/archiv/{_e(ordner)}/{f.name}'><img src='/archiv/{_e(ordner)}/{f.name}'></a>"
                            for f in fotos) +
                    "</div><p class='dim'>Fotos ungedreht, so wie sie von der Kamera kommen.</p>"
                    f"<pre>{_e(json.dumps(e, ensure_ascii=False, indent=1))}</pre></body></html>")

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _senden(self, code, typ, daten: bytes):
                self.send_response(code)
                self.send_header("Content-Type", typ)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(daten)

            def _weiter(self, ziel="/"):
                self.send_response(303)
                self.send_header("Location", ziel)
                self.end_headers()

            def do_GET(self):
                pfad = self.path.split("?")[0]
                if pfad == "/":
                    self._senden(200, "text/html; charset=utf-8", startseite().encode())
                elif pfad == "/zustand.json":
                    self._senden(200, "application/json", json.dumps(d.zustand, ensure_ascii=False).encode())
                elif pfad.startswith("/bild/"):
                    j = d.bilder.get(pfad[6:])
                    self._senden(200, "image/jpeg", j) if j else self._senden(404, "text/plain", b"kein Bild")
                elif pfad.startswith("/messung/"):
                    seite = messung(pfad[9:])
                    if seite:
                        self._senden(200, "text/html; charset=utf-8", seite.encode())
                    else:
                        self._senden(404, "text/plain", b"nicht gefunden")
                elif pfad.startswith("/archiv/"):
                    p = d.archiv.datei(pfad[8:])
                    if p and p.suffix in (".jpg", ".json"):
                        self._senden(200, "image/jpeg" if p.suffix == ".jpg" else "application/json", p.read_bytes())
                    else:
                        self._senden(404, "text/plain", b"nicht gefunden")
                else:
                    self._senden(404, "text/plain", b"nicht gefunden")

            def do_POST(self):
                laenge = int(self.headers.get("Content-Length") or 0)
                daten = parse_qs(self.rfile.read(laenge).decode()) if laenge else {}
                if self.path == "/messen":
                    d.sofort.set()
                    self._weiter()
                elif self.path == "/setzen":
                    try:
                        d.setzen(float(daten.get("wert", [""])[0].replace(",", ".")))
                    except ValueError:
                        return self._senden(400, "text/plain; charset=utf-8", "Kein gültiger Wert".encode())
                    self._weiter()
                else:
                    self._senden(404, "text/plain", b"nicht gefunden")

        self.server = ThreadingHTTPServer(("0.0.0.0", self.port), H)

    def starten(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
