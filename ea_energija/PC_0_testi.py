"""PC (PyCharm): PREIZKUS NAMESTITVE. Požene vse teste, ki ne potrebujejo
strojne opreme. Vsi morajo končati z OK.

V PyCharmu: Run. Ob prvem zagonu na novem računalniku (in po vsaki posodobitvi
kode) pregleda, da skripte za zajem in analizo delujejo.
"""
import os
import sys
import unittest

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

paketi = ["test_zajem", "test_naprava", "test_stari_zapisi", "test_skripte"]
rezultat = unittest.TextTestRunner(verbosity=1).run(
    unittest.defaultTestLoader.loadTestsFromNames(paketi))
if rezultat.wasSuccessful():
    print("\nVSI TESTI V REDU. (Testi jedra algoritmov v gostitelj/ potrebujejo prevajalnik C++ "
          "in se poženejo na Macu.)")
sys.exit(0 if rezultat.wasSuccessful() else 1)
