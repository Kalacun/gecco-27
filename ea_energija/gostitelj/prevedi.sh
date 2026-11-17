#!/bin/sh
# Prevede gostiteljski program iz istega jedra kot firmware (ea_jedro.h).
# -ffp-contract=fast: prevajalnik za ESP32 združuje množenje in seštevanje
# (ukaz madd.s); enako dovolimo tudi tu, da so zaokrožitve čim bolj podobne.
# Dodatne možnosti prevajalnika: ./prevedi.sh -DOPT_S=2
set -e
cd "$(dirname "$0")"
${CXX:-c++} -std=c++17 -O2 -ffp-contract=fast -Wall -Wextra -Wdouble-promotion \
    -Wfloat-conversion "$@" -o ea_gostitelj gostitelj.cpp
