#!/usr/bin/env bash
# Telefon köprüsü kurulumu (Mac'te, Docker DIŞINDA, bir kez).
# iOS otomasyonu Apple araçları (Xcode) gerektirdiği için Docker içinde çalışamaz.
set -euo pipefail

command -v brew >/dev/null || { echo "Homebrew gerekli: https://brew.sh"; exit 1; }
brew install node ffmpeg
brew install --cask android-platform-tools   # adb (Android)
npm install -g appium
appium driver install xcuitest      || appium driver update xcuitest
appium driver install uiautomator2  || appium driver update uiautomator2

echo
echo "Kuruldu. iOS için ek adımlar:"
echo "  1) Xcode (App Store) kurulu olmalı, bir kez açılıp lisans kabul edilmeli."
echo "  2) iPhone: Ayarlar > Gizlilik ve Güvenlik > Geliştirici Modu: Açık"
echo "  3) WebDriverAgent imzası: appium driver run xcuitest open-wda  (Xcode'da Team seçip iPhone'a bir kez çalıştırın)"
echo "Android için: telefonda Geliştirici seçenekleri > USB hata ayıklama: Açık, sonra 'adb devices' ile görün."
echo
echo "Sonra köprüyü başlatın: ./host/kopru-baslat.sh"
