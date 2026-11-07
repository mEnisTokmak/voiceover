#!/usr/bin/env bash
# Telefon köprüsünü başlatır: Docker içindeki sistem bu adrese bağlanır (host.docker.internal:4723).
set -euo pipefail
echo "Bağlı Android cihazlar:"; adb devices 2>/dev/null || echo "  (adb yok)"
echo "Bağlı iOS cihazlar:"; xcrun xctrace list devices 2>/dev/null | grep -v Simulator | sed -n '1,20p' || true
echo
exec appium --address 0.0.0.0 --port 4723
