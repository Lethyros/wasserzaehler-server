#!/bin/bash
# Im Container als root ausführen. Quelle = hochkopiertes Projekt (siehe deploy.sh).
# Pakete, Benutzer, /opt/wasserzaehler, Python-Umgebung, systemd-Dienst.
set -euo pipefail
QUELLE="$(cd "$(dirname "$0")/.." && pwd)"
ZIEL=/opt/wasserzaehler

echo "== Pakete"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3-venv rsync ca-certificates >/dev/null

echo "== Benutzer"
id wasserzaehler >/dev/null 2>&1 || useradd --system --home /var/lib/wasserzaehler --shell /usr/sbin/nologin wasserzaehler
install -d -o wasserzaehler -g wasserzaehler /var/lib/wasserzaehler

echo "== Programm nach $ZIEL"
mkdir -p "$ZIEL"
# config.toml, referenz.jpg und modelle/ gehören der Installation (kommen von "wasserzaehler uebernehmen")
rsync -a --delete --exclude venv --exclude config.toml --exclude referenz.jpg --exclude modelle \
    --exclude tests --exclude system --exclude docs --exclude .git --exclude __pycache__ "$QUELLE/" "$ZIEL/"

echo "== Python-Umgebung"
[ -d "$ZIEL/venv" ] || python3 -m venv "$ZIEL/venv"
"$ZIEL/venv/bin/pip" install -q --upgrade pip
"$ZIEL/venv/bin/pip" install -q opencv-python-headless numpy paho-mqtt ai-edge-litert

echo "== Zugangsdaten"
if [ ! -f /etc/wasserzaehler.env ]; then
    install -m 600 /dev/null /etc/wasserzaehler.env
    printf 'WASSERZAEHLER_MQTT_BENUTZER=\nWASSERZAEHLER_MQTT_PASSWORT=\n' > /etc/wasserzaehler.env
    echo "   /etc/wasserzaehler.env angelegt – MQTT-Benutzer/Passwort eintragen!"
fi

echo "== Dienst"
install -m 644 "$QUELLE/system/wasserzaehler.service" /etc/systemd/system/wasserzaehler.service
cat > /usr/local/bin/wasserzaehler <<'EOF2'
#!/bin/sh
cd /opt/wasserzaehler && exec /opt/wasserzaehler/venv/bin/python -m wasserzaehler -c /opt/wasserzaehler/config.toml "$@"
EOF2
chmod 755 /usr/local/bin/wasserzaehler
chown -R root:root "$ZIEL"
systemctl daemon-reload
systemctl enable wasserzaehler.service
echo
if [ -f "$ZIEL/config.toml" ]; then
    echo "Fertig. Start: systemctl restart wasserzaehler; Log: journalctl -u wasserzaehler -f"
else
    echo "Fertig. Noch keine Konfiguration – einmalig von der Kamera übernehmen:"
    echo "  wasserzaehler uebernehmen <IP der ESP32-CAM>"
    echo "  nano /opt/wasserzaehler/config.toml        (MQTT-Host eintragen)"
    echo "  nano /etc/wasserzaehler.env                (MQTT-Benutzer/Passwort)"
    echo "  systemctl restart wasserzaehler"
fi
