#!/bin/bash
set -euo pipefail
# Run as root from the reviewed, extracted collector bundle.
test "$(id -u)" = 0
test -f collector.env
test -f server.crt
test -f server.key
umask 022
if test -e /opt/sabc-collector; then
  echo 'Collector path already exists; inspect it before applying an upgrade.' >&2
  exit 1
fi
if getent passwd sabc-collector >/dev/null; then
  echo 'Collector account already exists; inspect before reuse.' >&2
  exit 1
fi
apt-get update
apt-get install -y python3-venv
useradd --system --home-dir /var/lib/sabc-collector --shell /usr/sbin/nologin sabc-collector
install -d -m 755 /opt/sabc-collector
install -d -m 750 -o root -g sabc-collector /etc/sabc-collector
install -d -m 700 -o sabc-collector -g sabc-collector /var/lib/sabc-collector
cp -R sabc /opt/sabc-collector/sabc
chmod -R a+rX /opt/sabc-collector/sabc
install -m 644 requirements.txt /opt/sabc-collector/requirements.txt
/usr/bin/python3 -m venv /opt/sabc-collector/venv
/opt/sabc-collector/venv/bin/pip install --no-cache-dir -r /opt/sabc-collector/requirements.txt
install -m 600 -o root -g root collector.env /etc/sabc-collector/environment
install -m 640 -o root -g sabc-collector server.key /etc/sabc-collector/server.key
install -m 644 -o root -g root server.crt /etc/sabc-collector/server.crt
install -m 644 sabc-collector.service /etc/systemd/system/sabc-collector.service
systemctl daemon-reload
systemctl enable --now sabc-collector
systemctl is-active sabc-collector
