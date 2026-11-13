// Primer nastavitev za pošiljanje rezultatov prek WiFi (WIFI_POSILJANJE 1).
// Skopirajte to datoteko v "wifi_nastavitve.h" in vpišite svoje podatke.
// wifi_nastavitve.h je v .gitignore, zato gesla ne pridejo v git.
#pragma once

// Omrežje 2,4 GHz, WPA2-Personal (ESP32 ne podpira 5 GHz; eduroam /
// WPA2-Enterprise ne bo delal - uporabite domači usmerjevalnik ali
// dostopno točko telefona/računalnika).
#define WIFI_SSID   "ime_omrezja"
#define WIFI_GESLO  "geslo_omrezja"

// Naslov računalnika, na katerem teče succulent (streznik.py).
// IP poiščete na macOS z "ipconfig getifaddr en0", na Linuxu z "ip addr",
// na Windows z "ipconfig". Najbolje, da ga v usmerjevalniku rezervirate.
#define SUCC_URL    "http://192.168.1.50:8080/measure"

// Mora biti enako kot "password" v succulent_streznik/configuration.yml.
#define SUCC_GESLO  "spremeni-me"

// Moč oddajanja: nižja moč = nižje tokovne konice (manj padca napetosti).
// Možnosti: WIFI_POWER_19_5dBm (največ), ..., WIFI_POWER_8_5dBm, WIFI_POWER_2dBm
#define WIFI_MOC_ODDAJANJA  WIFI_POWER_8_5dBm
