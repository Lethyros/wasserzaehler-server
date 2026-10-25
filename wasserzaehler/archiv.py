"""Jede Messung mit Fotos und Ergebnis ablegen – zum Nachprüfen und zum Kalibrieren.

  <archiv>/2026-10-24/231846/foto1.jpg …   Original-JPEGs der Kamera (ungedreht)
  <archiv>/2026-10-24/231846/ergebnis.json Einzelwerte, Vertrauen, Status
"""

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class Archiv:
    def __init__(self, pfad: Path, tage: int):
        self.pfad = Path(pfad)
        self.tage = tage
        self.pfad.mkdir(parents=True, exist_ok=True)

    def ablegen(self, zeit: datetime, fotos: list[bytes], ergebnis: dict) -> str:
        # Ordnernamen in UTC – in Ortszeit gibt es die Stunde der Zeitumstellung zweimal
        utc = zeit.astimezone(timezone.utc)
        ordner = self.pfad / utc.strftime("%Y-%m-%d") / utc.strftime("%H%M%SZ")
        ordner.mkdir(parents=True, exist_ok=True)
        for i, j in enumerate(fotos, 1):
            (ordner / f"foto{i}.jpg").write_bytes(j)
        tmp = ordner / "ergebnis.json.tmp"
        tmp.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1))
        tmp.replace(ordner / "ergebnis.json")
        return str(ordner.relative_to(self.pfad))

    def aufraeumen(self):
        grenze = (datetime.now() - timedelta(days=self.tage)).strftime("%Y-%m-%d")
        for tag in self.pfad.iterdir():
            if tag.is_dir() and tag.name < grenze:
                shutil.rmtree(tag, ignore_errors=True)
                log.info("Archiv %s gelöscht (älter als %d Tage)", tag.name, self.tage)

    def letzte(self, anzahl: int = 50) -> list[dict]:
        """Neueste Messungen, sortiert nach der echten Zeit (alte Ordner sind noch in Ortszeit benannt)."""
        aus = []
        for tag in sorted((t for t in self.pfad.iterdir() if t.is_dir()), reverse=True):
            for m in (m for m in tag.iterdir() if m.is_dir()):
                try:
                    e = json.loads((m / "ergebnis.json").read_text())
                    e["_t"] = datetime.fromisoformat(e["zeit"])
                except (OSError, ValueError, KeyError):
                    continue
                e["ordner"] = f"{tag.name}/{m.name}"
                aus.append(e)
            if len(aus) >= anzahl + 300:  # ein Tag Puffer, Tage überlappen bei Ortszeit-Namen
                break
        aus.sort(key=lambda e: e.pop("_t"), reverse=True)
        return aus[:anzahl]

    def alle_ergebnisse(self):
        for f in sorted(self.pfad.glob("*/*/ergebnis.json")):
            try:
                yield json.loads(f.read_text())
            except (OSError, ValueError):
                continue

    def datei(self, relativ: str) -> Path | None:
        """Pfad einer Archivdatei für die Webseite – nur innerhalb des Archivs."""
        p = (self.pfad / relativ).resolve()
        return p if p.is_file() and self.pfad.resolve() in p.parents else None
