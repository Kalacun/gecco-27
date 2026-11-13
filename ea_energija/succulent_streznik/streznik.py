#!/usr/bin/env python3
"""Strežnik succulent, ki sprejema rezultate z ESP32 (WIFI_POSILJANJE 1).

    pip install succulent          (Python 3.10-3.13)
    python streznik.py

Podatki se shranjujejo v data/data.csv v tej mapi (ena vrstica na zagon).
Iz njih "python zajem.py succulent ..." naredi esp32.txt za analizo.
"""
from succulent.api import SucculentAPI

# 0.0.0.0 = sprejemaj povezave iz lokalnega omrežja (ne samo z localhost)
api = SucculentAPI(host="0.0.0.0", port=8080, config="configuration.yml", format="csv")
api.start()
