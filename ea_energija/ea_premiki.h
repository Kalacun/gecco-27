// ====================================================================
//  ea_premiki.h - USTVARJENO z generiraj_premike.py; NE UREJAJTE ROČNO.
//  Fiksni vektorji premika optimuma (v flashu, enaki za vse algoritme
//  in vse zagone). Pravilo in seme sta opisana v generiraj_premike.py.
//  OSNOVNO_SEME = 20270101; komponente: 20-80 % polovičnega razpona,
//  naključen predznak. Preverjanje: python3 generiraj_premike.py --preveri
// ====================================================================
#pragma once
#define PREMIK_SEME 20270101u   // seme, iz katerega so ustvarjeni premiki

// Rastrigin, D = 10
static const float PREMIK_F0_D10[10] = {
  1.26709557f, -3.47662234f, 4.08124733f, -1.81588745f, -1.86843967f,
  1.79895425f, -2.65505815f, -2.78118229f, -3.24338531f, -3.9355278f,
};

// Rastrigin, D = 20
static const float PREMIK_F0_D20[20] = {
  3.55666375f, 3.26264524f, -2.9508698f, 1.6260711f, 2.47031069f,
  -1.50281262f, 2.90633225f, -2.50466609f, -2.631145f, -1.57110727f,
  2.09756112f, 1.31081748f, 2.02059865f, -1.72579515f, 2.05546188f,
  -1.2221626f, -3.98408937f, 2.95097423f, 1.56593227f, -3.41696548f,
};

// Rosenbrock, D = 10
static const float PREMIK_F1_D10[10] = {
  -7.25117922f, -8.22796631f, -9.66792202f, 12.1244373f, -13.8113718f,
  19.4517746f, -17.2964325f, 9.7243576f, -10.8797483f, 15.2983618f,
};

// Rosenbrock, D = 20
static const float PREMIK_F1_D20[20] = {
  -8.27953625f, 15.5938873f, 6.68243885f, 10.0393801f, 23.8058853f,
  -15.9781981f, -15.4511213f, -16.7216434f, -16.1583004f, 18.3395081f,
  -14.8742418f, -6.66163206f, -20.9291115f, 9.28540421f, 11.7001467f,
  10.1674623f, 15.4719753f, -20.7190838f, -17.8826504f, 17.5403557f,
};

// Vrne tabelo premika za (funkcija, D) ali NULL, če je ni.
static inline const float *premik_za(int funkcija, int d) {
  if (funkcija == 0 && d == 10) return PREMIK_F0_D10;
  if (funkcija == 0 && d == 20) return PREMIK_F0_D20;
  if (funkcija == 1 && d == 10) return PREMIK_F1_D10;
  if (funkcija == 1 && d == 20) return PREMIK_F1_D20;
  return NULL;
}
