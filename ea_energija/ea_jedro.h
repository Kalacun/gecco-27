// ====================================================================
//  ea_jedro.h - jedro algoritmov (DE, jDE, L-SHADE), SKUPNO za ESP32 in
//  za prevod na računalniku (mapa gostitelj/).
//
//  Vsebuje: parametre algoritmov, zapis zagona, pomnilnik, generator
//  naključnih števil, testni funkciji, spremljanje zagona in algoritme.
//  Ista izvorna koda in isti tip (float) na obeh platformah.
//
//  Pred vključitvijo mora biti določen SEME (osnovno seme). Čas daje
//  funkcija int64_t ea_cas_us(void): monotoni 64-bitni čas v mikrosekundah.
//  Na ESP32 je to esp_timer_get_time() (spodaj); gostiteljski program
//  določi svojo.
// ====================================================================
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <algorithm>

#ifdef ARDUINO
#include "esp_timer.h"
static inline int64_t ea_cas_us(void) { return esp_timer_get_time(); }
#endif

// ---- parametri klasičnega DE (DE/rand/1/bin) ----
#define DE_NP      100
#define DE_F       0.5f
#define DE_CR      0.9f

// ---- parametri jDE (Brest in sod., 2006) ----
#define JDE_NP     100
#define JDE_TAU1   0.1f
#define JDE_TAU2   0.1f
#define JDE_FL     0.1f
#define JDE_FU     0.9f

// ---- parametri L-SHADE (Tanabe in Fukunaga, 2014) ----
// NP_init = 18 * D kot v originalu, brez omejitve. Pomnilnik za populacijo,
// poskusne vektorje in arhiv (2,6 * NP_init vrstic) je pri D = 20 okoli
// 154 kB; če ga ni dovolj, alociraj() vrne false in se poskus NE izvede
// (nikoli se tiho ne zmanjša populacija).
#define ls_np_init(d) (18 * (d))
#define LS_NP_MIN   4
#define LS_H        6       // velikost zgodovinskega spomina
#define LS_P        0.11f   // delež najboljših za current-to-pbest
#define LS_RARC     2.6f    // velikost arhiva = LS_RARC * NP

#define PI_F     3.14159265f

#include "ea_premiki.h"   // fiksni vektorji premika optimuma (ustvarjena datoteka)

// ---- proračun, cilji in kontrolne točke (ENAKO za vse algoritme) ----
#define NACIN_FE    0       // ustavi pri FE_max evalvacijah
#define NACIN_CAS   1       // ustavi po času T
// Lestvica ciljev: f - f* <= CILJI[k] (f* = 0). Od najlažjega k najtežjemu.
#define ST_CILJEV   6
static const float CILJI[ST_CILJEV] = {1e1f, 1e0f, 1e-1f, 1e-2f, 1e-3f, 1e-4f};
// Kontrolne točke: v načinu FE pri FE = FE_max * k / ST_TOCK, v načinu CAS
// pri t = T * k / ST_TOCK (k = 1..ST_TOCK); zadnja je konec proračuna.
#define ST_TOCK     20
// V načinu CAS se ura prebere vsakih PERIODA_URE_FE evalvacij (za vse
// algoritme enako). Zagon se zato konča največ toliko evalvacij po T.
#define PERIODA_URE_FE 16

struct Rezultat {          // en zagon enega algoritma (zapiše se v flash)
  uint8_t  alg;            // 0 = DE, 1 = jDE, 2 = L-SHADE
  uint8_t  zagon;          // številka bloka (ponovitve); ogrevanje: 0..OGREVANJE-1
  uint8_t  poskus;         // indeks v POSKUSI
  uint8_t  poz;            // položaj algoritma v bloku (0 = prvi)
  uint8_t  ogrev;          // 1 = ogrevalni zagon (ne analizira se)
  uint8_t  nacin;          // NACIN_FE ali NACIN_CAS
  uint8_t  st_tock;        // število zapisanih kontrolnih točk
  uint8_t  rezerva;
  uint16_t np_konec;       // velikost populacije ob koncu (L-SHADE jo manjša)
  uint32_t seme;           // seme generatorja za ta zagon (seme_zagona)
  uint32_t proracun_fe;    // NACIN_FE: FE_max (sicer 0)
  uint64_t proracun_us;    // NACIN_CAS: T v mikrosekundah (sicer 0)
  uint64_t t_zacetek_us;   // vrednost časovnika ob začetku optimizacije
  uint64_t t_konec_us;     // vrednost časovnika ob koncu optimizacije
  uint32_t fe;             // skupno število evalvacij
  uint32_t gen;            // število DOKONČANIH generacij (s selekcijo)
  float    best;           // najboljša najdena vrednost
  uint32_t cilj_fe[ST_CILJEV];    // prvi doseg cilja k: evalvacija (0 = ni dosežen)
  uint64_t cilj_us[ST_CILJEV];    //   in čas od začetka (us)
  uint32_t tocka_fe[ST_TOCK];     // kontrolna točka k: evalvacija,
  uint64_t tocka_us[ST_TOCK];     //   čas od začetka (us)
  float    tocka_best[ST_TOCK];   //   in najboljša vrednost do takrat
};

// ======================= TRENUTNI POSKUS ============================
int   D;                   // dimenzija
int   FUN;                 // 0 = Rastrigin, 1 = Rosenbrock
float SPOD, ZGOR;          // meje iskalnega prostora
int   LS_NP_INIT;          // začetna populacija L-SHADE pri tem D
int   NP_MAX, ARH_MAX;     // velikosti alociranih tabel
const float *PREMIK;       // premik optimuma o (tabela v flashu), dolžine D
float *OM;                 // odštevanec v kriteriju: o (Rastrigin) ali o - 1 (Rosenbrock)

// Nastavi problem: funkcija (0 = Rastrigin, 1 = Rosenbrock) in dimenzija.
// Enako za ESP32 in gostitelja. Vrne false, če za (funkcija, D) ni tabele
// premika v ea_premiki.h; tak poskus se ne sme izvesti.
bool nastavi_problem(int funkcija, int d) {
  FUN = funkcija;
  D = d;
  SPOD = (FUN == 0) ? -5.12f : -30.0f;
  ZGOR = (FUN == 0) ?  5.12f :  30.0f;
  LS_NP_INIT = ls_np_init(D);
  NP_MAX = std::max(std::max(DE_NP, JDE_NP), LS_NP_INIT);
  ARH_MAX = (int)(LS_RARC * LS_NP_INIT) + 1;
  PREMIK = premik_za(FUN, D);
  return PREMIK != NULL;
}

// ======================= POMNILNIK ALGORITMOV =======================
// Populacijo hranimo kot polje kazalcev na vrstice: ob selekciji samo
// zamenjamo kazalca, vrstice pa so majhne, zato ne potrebujemo velikega
// neprekinjenega bloka. Alociramo ENKRAT na poskus, izven merilnih oken.
float **X, **U, **A;        // populacija, poskusni vektorji, arhiv
float *fx, *fu;             // vrednosti kriterijske funkcije
float *Fpar, *CRpar;        // F in CR posameznikov (jDE)
float *Ftr, *CRtr;          // F in CR, uporabljena za poskusni vektor
int   *idx;                 // indeksi, urejeni po kakovosti (L-SHADE)
float *SF, *SCR, *Sdf;      // uspešni F, CR in izboljšave (L-SHADE)

void sprosti() {
  if (A) { for (int i = 0; i < ARH_MAX; i++) free(A[i]); free(A); }
  if (X) for (int i = 0; i < NP_MAX; i++) free(X[i]);
  if (U) for (int i = 0; i < NP_MAX; i++) free(U[i]);
  free(X); free(U);
  free(fx); free(fu); free(Fpar); free(CRpar); free(Ftr); free(CRtr);
  free(idx); free(SF); free(SCR); free(Sdf); free(OM);
  X = U = A = NULL;
  fx = fu = Fpar = CRpar = Ftr = CRtr = SF = SCR = Sdf = OM = NULL;
  idx = NULL;
}

bool alociraj() {
  X = (float **)calloc(NP_MAX, sizeof(float *));
  U = (float **)calloc(NP_MAX, sizeof(float *));
  A = (float **)calloc(ARH_MAX, sizeof(float *));
  if (!X || !U || !A) return false;
  for (int i = 0; i < NP_MAX; i++) {
    X[i] = (float *)malloc(D * sizeof(float));
    U[i] = (float *)malloc(D * sizeof(float));
    if (!X[i] || !U[i]) return false;
  }
  for (int i = 0; i < ARH_MAX; i++) {
    A[i] = (float *)malloc(D * sizeof(float));
    if (!A[i]) return false;
  }
  fx = (float *)malloc(NP_MAX * sizeof(float));
  fu = (float *)malloc(NP_MAX * sizeof(float));
  Fpar = (float *)malloc(NP_MAX * sizeof(float));
  CRpar = (float *)malloc(NP_MAX * sizeof(float));
  Ftr = (float *)malloc(NP_MAX * sizeof(float));
  CRtr = (float *)malloc(NP_MAX * sizeof(float));
  idx = (int *)malloc(NP_MAX * sizeof(int));
  SF = (float *)malloc(NP_MAX * sizeof(float));
  SCR = (float *)malloc(NP_MAX * sizeof(float));
  Sdf = (float *)malloc(NP_MAX * sizeof(float));
  OM = (float *)malloc(D * sizeof(float));
  if (!(fx && fu && Fpar && CRpar && Ftr && CRtr && idx && SF && SCR && Sdf && OM && PREMIK))
    return false;
  // Rosenbrock ima nepremaknjen optimum v (1, ..., 1): z = x - o + 1 = x - (o - 1).
  for (int j = 0; j < D; j++) OM[j] = (FUN == 0) ? PREMIK[j] : PREMIK[j] - 1.0f;
  return true;
}

// ======================= NAKLJUČNA ŠTEVILA ==========================
// EN generator za vse algoritme: xoshiro128++ 1.0 (D. Blackman in
// S. Vigna, javna last, prng.di.unimi.it/xoshiro128plusplus.c). Stanje
// 128 bitov, perioda 2^128 - 1; samo 32-bitni premiki, rotacije, XOR in
// seštevanja (brez množenja in brez 64-bitnih operacij). Stanje nikoli
// ne sme biti povsod nič.
uint32_t rng_s[4];
static inline uint32_t rng_rotl(uint32_t x, int k) { return (x << k) | (x >> (32 - k)); }
inline uint32_t rnd_u32() {
  const uint32_t rezultat = rng_rotl(rng_s[0] + rng_s[3], 7) + rng_s[0];
  const uint32_t t = rng_s[1] << 9;
  rng_s[2] ^= rng_s[0];
  rng_s[3] ^= rng_s[1];
  rng_s[1] ^= rng_s[2];
  rng_s[0] ^= rng_s[3];
  rng_s[2] ^= t;
  rng_s[3] = rng_rotl(rng_s[3], 11);
  return rezultat;
}
// Enakomerno v [0, 1): zgornjih 24 bitov krat 2^-24. Največja vrednost je
// (2^24 - 1) / 2^24 = 0,99999994 in je natančno predstavljiva; 1,0 ni mogoča.
inline float rnd() { return (rnd_u32() >> 8) * (1.0f / 16777216.0f); }
// Celo število v [0, n): odrez produkta rnd() * n. Za n < 2^24 produkt
// nikoli ne doseže n (preverjeno na gostitelju); pristranskost največ n / 2^24.
inline int rndi(int n) { return (int)(rnd() * n); }

// Mešalna funkcija za semena: bijekcija na 32 bitih ("lowbias32",
// C. Wellons, hash-prospector). Uporablja se SAMO pri nastavljanju semena.
static inline uint32_t mesaj32(uint32_t x) {
  x ^= x >> 16; x *= 0x7feb352dU;
  x ^= x >> 15; x *= 0x846ca68bU;
  x ^= x >> 16;
  return x;
}

// PRAVILO ZA SEME ZAGONA (zapiše se v vsak zapis):
//   seme = mesaj32( mesaj32(osnovno) XOR (poskus << 16 | blok << 8 | ogrev) )
// Seme je odvisno samo od osnovnega semena, poskusa (0..255), bloka
// (0..255) in oznake ogrevanja, NE od algoritma: vsi algoritmi istega
// bloka dobijo isto zaporedje (skupna naključna števila). Ker je mesaj32
// bijekcija, imajo različne trojke (poskus, blok, ogrev) različna semena.
// Brez strojnega generatorja in brez časa.
inline uint32_t seme_zagona(uint32_t osnovno, int poskus, int zagon, bool ogrev) {
  uint32_t w = ((uint32_t)(poskus & 0xff) << 16) | ((uint32_t)(zagon & 0xff) << 8) |
               (ogrev ? 1u : 0u);
  return mesaj32(mesaj32(osnovno) ^ w);
}

// Stanje generatorja iz 32-bitnega semena: štiri zaporedne vrednosti
// mesaj32(seme + k * 0x9E3779B9), k = 1..4.
inline void rng_nastavi(uint32_t seme) {
  for (int k = 0; k < 4; k++) rng_s[k] = mesaj32(seme + (uint32_t)(k + 1) * 0x9E3779B9u);
  if ((rng_s[0] | rng_s[1] | rng_s[2] | rng_s[3]) == 0) rng_s[0] = 1;
}

// ======================= VRSTNI RED ALGORITMOV V BLOKU ==============
// V vsakem bloku teče vsak algoritem enkrat. Vrstni red je določen z
// dokumentiranim determinističnim pravilom (brez strojnega generatorja in
// brez časa) in se za vsak zagon zapiše (polje poz). Generator za vrstni
// red je ločen od generatorja algoritmov.
#define RED_NAKLJUCNI    0   // neodvisna naključna permutacija za vsak blok
#define RED_URAVNOTEZEN  1   // vsaka permutacija enako pogosto, premešano

// Permutacija številka st (leksikografski vrstni red) n elementov 0..n-1.
inline void permutacija_st(int st, int n, uint8_t *izhod) {
  uint8_t prosti[8];
  int fakt = 1;
  for (int i = 0; i < n; i++) prosti[i] = (uint8_t)i;
  for (int i = 2; i < n; i++) fakt *= i;               // (n-1)!
  for (int i = 0; i < n; i++) {
    int k = st / fakt;
    st %= fakt;
    izhod[i] = prosti[k];
    for (int j = k; j < n - 1 - i; j++) prosti[j] = prosti[j + 1];
    if (n - 1 - i > 0) fakt /= (n - 1 - i);
  }
}

// RED_NAKLJUCNI: Fisher-Yatesovo mešanje 0..n-1 z vrednostmi
//   h0 = mesaj32( mesaj32(osnovno XOR 0xB10C0DE5) XOR (poskus << 16 | blok << 8) )
//   h  = mesaj32(h + 0x9E3779B9) pred vsako zamenjavo, j = h mod (i + 1).
// Pristranskost ostanka je pod 2^-30. Bloki so med seboj neodvisni.
inline void red_nakljucni(uint32_t osnovno, int poskus, int blok, int n, uint8_t *izhod) {
  for (int i = 0; i < n; i++) izhod[i] = (uint8_t)i;
  uint32_t h = mesaj32(mesaj32(osnovno ^ 0xB10C0DE5u) ^
                       (((uint32_t)(poskus & 0xff) << 16) | ((uint32_t)(blok & 0xff) << 8)));
  for (int i = n - 1; i > 0; i--) {
    h = mesaj32(h + 0x9E3779B9u);
    int j = (int)(h % (uint32_t)(i + 1));
    uint8_t t = izhod[i]; izhod[i] = izhod[j]; izhod[j] = t;
  }
}

// RED_URAVNOTEZEN: številke permutacij za bloke 0..zagonov-1. Vsaka od n!
// permutacij nastopi natanko zagonov / n!-krat; zaporedje je premešano s
// Fisher-Yatesom in istim tokom h kot zgoraj (blok = 255). Vrne false, če
// zagonov ni večkratnik n! (takrat uravnoteženje ni mogoče).
inline bool red_uravnotezen(uint32_t osnovno, int poskus, int zagonov, int n, uint8_t *st_perm) {
  int n_perm = 1;
  for (int i = 2; i <= n; i++) n_perm *= i;
  if (zagonov % n_perm != 0) return false;
  for (int z = 0; z < zagonov; z++) st_perm[z] = (uint8_t)(z % n_perm);
  uint32_t h = mesaj32(mesaj32(osnovno ^ 0xB10C0DE5u) ^
                       (((uint32_t)(poskus & 0xff) << 16) | (255u << 8)));
  for (int z = zagonov - 1; z > 0; z--) {
    h = mesaj32(h + 0x9E3779B9u);
    int j = (int)(h % (uint32_t)(z + 1));
    uint8_t t = st_perm[z]; st_perm[z] = st_perm[j]; st_perm[j] = t;
  }
  return true;
}

// Normalna porazdelitev N(m, s) - Box-Mullerjeva transformacija
float rnd_normal(float m, float s) {
  float u1 = rnd();
  if (u1 < 1e-7f) u1 = 1e-7f;          // log(0) ni definiran
  return m + s * sqrtf(-2.0f * logf(u1)) * cosf(2.0f * PI_F * rnd());
}

// Cauchyjeva porazdelitev C(m, s)
float rnd_cauchy(float m, float s) {
  return m + s * tanf(PI_F * (rnd() - 0.5f));
}

// ======================= TESTNI FUNKCIJI ============================
// PREMAKNJENI funkciji, f(x) = F(z):
//   Rastrigin:  z = x - o,      F(z) = 10 D + vsota (z_j^2 - 10 cos(2 pi z_j)),
//               meje [-5.12, 5.12], optimum v x = o
//   Rosenbrock: z = x - o + 1,  F(z) = vsota (100 (z_{j+1} - z_j^2)^2 + (1 - z_j)^2),
//               meje [-30, 30], optimum v x = o
// o je fiksen vektor iz ea_premiki.h (20-80 % polovičnega razpona, naključen
// predznak), enak za vse algoritme in zagone. Vrednost v optimumu je 0.
// Vse v float (ESP32 ima FPU samo za float). Premik stane eno odštevanje
// na komponento, enako za vse algoritme.
float kriterij(const float *x) {
  float s = 0.0f;
  if (FUN == 0) {                      // Rastrigin
    s = 10.0f * D;
    for (int j = 0; j < D; j++) {
      float z = x[j] - OM[j];
      s += z * z - 10.0f * cosf(2.0f * PI_F * z);
    }
  } else {                             // Rosenbrock
    float z0 = x[0] - OM[0];
    for (int j = 0; j < D - 1; j++) {
      float z1 = x[j + 1] - OM[j + 1];
      float a = z1 - z0 * z0;
      float b = 1.0f - z0;
      s += 100.0f * a * a + b * b;
      z0 = z1;
    }
  }
  return s;
}

// ======================= SPREMLJANJE ZAGONA =========================
// Skupno za vse algoritme. oceni() je EDINA pot do kriterijske funkcije
// in za vsako evalvacijo naredi natanko to, v tem vrstnem redu:
//   1) izračuna vrednost, 2) poveča števec evalvacij, 3) posodobi najboljšo
//   vrednost, 4) preveri cilje, 5) preveri kontrolno točko in proračun,
//   6) vrne vrednost.
// Ko je proračun porabljen, postavi sl.konec; algoritem se mora takoj po
// klicu oceni() vrniti (pravilo je enako za vse algoritme). Tako se zagon
// v načinu FE konča pri NATANKO FE_max evalvacijah, tudi sredi generacije.
struct Sledenje {
  int64_t  t0;                 // časovnik ob začetku (us)
  uint32_t fe;                 // število evalvacij
  uint32_t fe_meja;            // pri tej evalvaciji se pokliče ob_meji()
  float    best;               // najboljša vrednost doslej
  bool     konec;              // proračun je porabljen
  uint8_t  nacin;              // NACIN_FE ali NACIN_CAS
  uint8_t  k_cilj;             // naslednji še nedoseženi cilj
  uint8_t  k_tocka;            // naslednja kontrolna točka
  uint32_t gen;                // dokončane generacije
  uint32_t fe_max;             // NACIN_FE
  int64_t  t_max;              // NACIN_CAS (us)
  int64_t  t_zadnji;           // zadnji odčitek ure, od začetka (us)
  float    inv_fe_max;         // 1 / FE_max
  float    inv_t_max;          // 64 / T (t_zadnji se pred pretvorbo deli s 64)
  uint32_t tocka_fe_meja[ST_TOCK];   // NACIN_FE: evalvacije kontrolnih točk
  int64_t  tocka_us_meja[ST_TOCK];   // NACIN_CAS: časi kontrolnih točk
} sl;
Rezultat *trenutni;

// Prvi doseg enega ali več ciljev: uro preberemo enkrat.
void dosezen_cilj(float f) {
  uint64_t t = (uint64_t)(ea_cas_us() - sl.t0);
  while (sl.k_cilj < ST_CILJEV && f <= CILJI[sl.k_cilj]) {
    trenutni->cilj_fe[sl.k_cilj] = sl.fe;
    trenutni->cilj_us[sl.k_cilj] = t;
    sl.k_cilj++;
  }
}

// Pokliče se, ko števec evalvacij doseže sl.fe_meja: v načinu FE ob vsaki
// kontrolni točki (ST_TOCK-krat na zagon), v načinu CAS vsakih
// PERIODA_URE_FE evalvacij. Prebere uro, zapiše dosežene kontrolne točke
// (evalvacija, čas, najboljša vrednost) in preveri proračun.
void ob_meji() {
  int64_t t = ea_cas_us() - sl.t0;
  sl.t_zadnji = t;
  bool konec;
  if (sl.nacin == NACIN_FE) {
    while (sl.k_tocka < ST_TOCK && sl.fe >= sl.tocka_fe_meja[sl.k_tocka]) {
      trenutni->tocka_fe[sl.k_tocka] = sl.fe;
      trenutni->tocka_us[sl.k_tocka] = (uint64_t)t;
      trenutni->tocka_best[sl.k_tocka] = sl.best;
      sl.k_tocka++;
    }
    konec = sl.fe >= sl.fe_max;
    if (!konec) sl.fe_meja = sl.tocka_fe_meja[sl.k_tocka];
  } else {
    while (sl.k_tocka < ST_TOCK && t >= sl.tocka_us_meja[sl.k_tocka]) {
      trenutni->tocka_fe[sl.k_tocka] = sl.fe;
      trenutni->tocka_us[sl.k_tocka] = (uint64_t)t;
      trenutni->tocka_best[sl.k_tocka] = sl.best;
      sl.k_tocka++;
    }
    konec = t >= sl.t_max;
    if (!konec) sl.fe_meja = sl.fe + PERIODA_URE_FE;
  }
  if (konec) { sl.konec = true; sl.fe_meja = UINT32_MAX; }
}

inline float oceni(const float *x) {
  float f = kriterij(x);                         // 1) vrednost
  sl.fe++;                                       // 2) števec evalvacij
  if (f < sl.best) {                             // 3) najboljša vrednost (NaN ni izboljšava)
    sl.best = f;
    if (sl.k_cilj < ST_CILJEV && f <= CILJI[sl.k_cilj]) dosezen_cilj(f);   // 4) cilji
  }
  if (sl.fe >= sl.fe_meja) ob_meji();            // 5) kontrolna točka in proračun
  return f;                                      // 6)
}

// Porabljeni delež proračuna v [0, 1]: FE / FE_max v načinu FE, t / T v
// načinu CAS (t je zadnji odčitek ure v oceni(), star največ
// PERIODA_URE_FE evalvacij). Uporablja ga L-SHADE za velikost populacije.
inline float delez_proracuna() {
  float d = (sl.nacin == NACIN_FE) ? sl.fe * sl.inv_fe_max
                                   : (uint32_t)(sl.t_zadnji >> 6) * sl.inv_t_max;
  return d > 1.0f ? 1.0f : d;
}

inline void zamenjaj(float **a, float **b) { float *t = *a; *a = *b; *b = t; }

// Inicializacija populacije velikosti n (enakomerno v mejah). Začetne
// evalvacije štejejo v proračun.
void inicializiraj(int n) {
  for (int i = 0; i < n; i++) {
    for (int j = 0; j < D; j++) X[i][j] = SPOD + rnd() * (ZGOR - SPOD);
    fx[i] = oceni(X[i]);
    if (sl.konec) return;
  }
}

// ======================= DE in jDE ==================================
// Klasični DE/rand/1/bin s fiksnima F in CR. jDE je enak, le da ima
// vsak posameznik svoja F in CR, ki se samoprilagajata.
// Obravnava mej: komponenta izven mej -> naključna vrednost v mejah.
// Sinhrona različica: vsi poskusni vektorji generacije g se tvorijo
// iz populacije g, šele nato sledi selekcija.
int de_jde(bool jde) {
  const int NP = jde ? JDE_NP : DE_NP;
  inicializiraj(NP);
  if (sl.konec) return NP;
  for (int i = 0; i < NP; i++) { Fpar[i] = 0.5f; CRpar[i] = 0.9f; }

  for (;;) {
    for (int i = 0; i < NP; i++) {
      float F, CR;
      if (jde) {
        // jDE: z verjetnostjo tau1 nov F v [FL, FL+FU], z verjetnostjo
        // tau2 nov CR v [0, 1), sicer podedovana vrednost.
        F  = (rnd() < JDE_TAU1) ? JDE_FL + JDE_FU * rnd() : Fpar[i];
        CR = (rnd() < JDE_TAU2) ? rnd() : CRpar[i];
      } else {
        F = DE_F; CR = DE_CR;
      }
      Ftr[i] = F; CRtr[i] = CR;

      // trije različni naključni posamezniki, različni od i
      int r1, r2, r3;
      do r1 = rndi(NP); while (r1 == i);
      do r2 = rndi(NP); while (r2 == i || r2 == r1);
      do r3 = rndi(NP); while (r3 == i || r3 == r1 || r3 == r2);

      // mutacija DE/rand/1 + binomsko križanje
      int jr = rndi(D);                // vsaj ena komponenta iz mutanta
      float *u = U[i], *xi = X[i], *a = X[r1], *b = X[r2], *c = X[r3];
      for (int j = 0; j < D; j++) {
        if (j == jr || rnd() < CR) {
          float v = a[j] + F * (b[j] - c[j]);
          if (v < SPOD || v > ZGOR) v = SPOD + rnd() * (ZGOR - SPOD);
          u[j] = v;
        } else {
          u[j] = xi[j];
        }
      }
      fu[i] = oceni(u);
      if (sl.konec) return NP;         // proračun porabljen (lahko sredi generacije)
    }
    // selekcija: boljši ali enak poskusni vektor zamenja starša
    for (int i = 0; i < NP; i++) {
      if (fu[i] <= fx[i]) {
        zamenjaj(&X[i], &U[i]);
        fx[i] = fu[i];
        if (jde) { Fpar[i] = Ftr[i]; CRpar[i] = CRtr[i]; }   // parametra preživita
      }
    }
    sl.gen++;
  }
}

// ======================= L-SHADE ====================================
// Tanabe & Fukunaga, "Improving the search performance of SHADE using
// linear population size reduction", IEEE CEC 2014.
//  - mutacija current-to-pbest/1 z arhivom,
//  - zgodovinski spomin M_F, M_CR velikosti H,
//  - F ~ Cauchy(M_F, 0.1), CR ~ N(M_CR, 0.1),
//  - posodobitev spomina z uteženo Lehmerjevo sredino,
//  - linearno zmanjševanje populacije (LPSR) od NP_init do NP_min.
// Velikost populacije sledi porabljenemu deležu proračuna, prebranemu PO
// evalvacijah generacije: v načinu FE je to FE / FE_max kot v originalu,
// v načinu CAS pa t / T (odstopanje od originala, ker je pogoj čas).
float *fx_sort;   // za primerjalno funkcijo qsort
int primerjaj(const void *a, const void *b) {
  float fa = fx_sort[*(const int *)a], fb = fx_sort[*(const int *)b];
  return (fa > fb) - (fa < fb);
}

int lshade() {
  int NP = LS_NP_INIT;
  inicializiraj(NP);

  float MF[LS_H], MCR[LS_H];           // MCR < 0 pomeni "terminalno" vrednost
  for (int h = 0; h < LS_H; h++) { MF[h] = 0.5f; MCR[h] = 0.5f; }
  if (sl.konec) return NP;
  int k = 0, nA = 0;

  for (;;) {
    // --- uredimo populacijo po kakovosti (za izbiro pbest) ---
    for (int i = 0; i < NP; i++) idx[i] = i;
    fx_sort = fx;
    qsort(idx, NP, sizeof(int), primerjaj);
    int pnum = (int)lroundf(LS_P * NP);
    if (pnum < 2) pnum = 2;

    // --- generiranje poskusnih vektorjev ---
    for (int i = 0; i < NP; i++) {
      int r = rndi(LS_H);
      float CR = (MCR[r] < 0) ? 0.0f : rnd_normal(MCR[r], 0.1f);
      if (CR < 0) CR = 0; else if (CR > 1) CR = 1;
      float F;
      do F = rnd_cauchy(MF[r], 0.1f); while (F <= 0);   // ponavljamo, dokler F <= 0
      if (F > 1) F = 1;
      Ftr[i] = F; CRtr[i] = CR;

      int pb = idx[rndi(pnum)];                          // eden izmed p% najboljših
      int r1; do r1 = rndi(NP); while (r1 == i);
      int r2; do r2 = rndi(NP + nA); while (r2 == i || r2 == r1);
      const float *xr2 = (r2 < NP) ? X[r2] : A[r2 - NP]; // iz populacije ali arhiva

      int jr = rndi(D);
      float *u = U[i], *xi = X[i], *xp = X[pb], *x1 = X[r1];
      for (int j = 0; j < D; j++) {
        if (j == jr || rnd() < CR) {
          float v = xi[j] + F * (xp[j] - xi[j]) + F * (x1[j] - xr2[j]);
          // obravnava mej kot v L-SHADE: polovica poti do meje
          if (v < SPOD) v = 0.5f * (SPOD + xi[j]);
          else if (v > ZGOR) v = 0.5f * (ZGOR + xi[j]);
          u[j] = v;
        } else {
          u[j] = xi[j];
        }
      }
      fu[i] = oceni(u);
      if (sl.konec) return NP;         // proračun porabljen (lahko sredi generacije)
    }

    // --- selekcija, arhiv in zbiranje uspešnih parametrov ---
    int Amax = (int)lroundf(LS_RARC * NP);
    int nS = 0;
    for (int i = 0; i < NP; i++) {
      if (fu[i] < fx[i]) {
        // starša shranimo v arhiv (če je poln, zamenjamo naključnega)
        float *cilj = (nA < Amax) ? A[nA++] : A[rndi(nA)];
        memcpy(cilj, X[i], D * sizeof(float));
        SF[nS] = Ftr[i]; SCR[nS] = CRtr[i]; Sdf[nS] = fx[i] - fu[i]; nS++;
      }
      if (fu[i] <= fx[i]) { zamenjaj(&X[i], &U[i]); fx[i] = fu[i]; }
    }

    // --- posodobitev zgodovinskega spomina (utežena Lehmerjeva sredina) ---
    if (nS > 0) {
      float vs = 0; for (int s = 0; s < nS; s++) vs += Sdf[s];
      float sF = 0, sF2 = 0, sC = 0, sC2 = 0, maxCR = 0;
      for (int s = 0; s < nS; s++) {
        float w = (vs > 0) ? Sdf[s] / vs : 1.0f / nS;
        sF += w * SF[s];  sF2 += w * SF[s] * SF[s];
        sC += w * SCR[s]; sC2 += w * SCR[s] * SCR[s];
        if (SCR[s] > maxCR) maxCR = SCR[s];
      }
      MF[k] = (sF > 0) ? sF2 / sF : MF[k];
      if (MCR[k] < 0 || maxCR == 0) MCR[k] = -1.0f;      // terminalna vrednost
      else MCR[k] = (sC > 0) ? sC2 / sC : MCR[k];
      k = (k + 1) % LS_H;
    }

    // --- linearno zmanjševanje populacije (glede na porabljeni proračun) ---
    float delez = delez_proracuna();
    int NPnov = (int)lroundf((LS_NP_MIN - LS_NP_INIT) * delez + LS_NP_INIT);
    if (NPnov < LS_NP_MIN) NPnov = LS_NP_MIN;
    while (NP > NPnov) {               // odstranimo najslabšega
      int w = 0;
      for (int i = 1; i < NP; i++) if (fx[i] > fx[w]) w = i;
      zamenjaj(&X[w], &X[NP - 1]);
      fx[w] = fx[NP - 1];
      NP--;
    }
    Amax = (int)lroundf(LS_RARC * NP);
    while (nA > Amax) {                // arhiv zmanjšamo z naključnim brisanjem
      int w = rndi(nA);
      zamenjaj(&A[w], &A[nA - 1]);
      nA--;
    }
    sl.gen++;
#ifdef EA_SLED                         // samo gostiteljski testi; na ESP32 ni prevedeno
    ea_sled_generacija(NP, nA);
#endif
  }
}

// ======================= EN ZAGON ===================================
// Seme je odvisno samo od poskusa in bloka (seme_zagona), zato vsi
// algoritmi v istem bloku dobijo isto zaporedje naključnih števil.
// nacin = NACIN_FE: proracun je FE_max; nacin = NACIN_CAS: proracun je T
// v mikrosekundah. Način in proračun sta parametra zagona (brez ponovnega
// prevajanja) in se zapišeta v zapis.
void pozeni(uint8_t alg, int poskus, int zagon, bool ogrev, uint8_t nacin,
            uint64_t proracun, Rezultat *r) {
  memset(r, 0, sizeof(*r));
  r->alg = alg; r->zagon = zagon; r->poskus = poskus; r->ogrev = ogrev;
  r->nacin = nacin;
  trenutni = r;
  r->seme = seme_zagona(SEME, poskus, zagon, ogrev);
  rng_nastavi(r->seme);

  memset(&sl, 0, sizeof(sl));
  sl.best = 1e30f;
  sl.nacin = nacin;
  if (nacin == NACIN_FE) {
    sl.fe_max = (uint32_t)proracun;
    r->proracun_fe = sl.fe_max;
    sl.inv_fe_max = 1.0f / sl.fe_max;
    for (int k = 0; k < ST_TOCK; k++) {
      uint32_t m = (uint32_t)((uint64_t)sl.fe_max * (k + 1) / ST_TOCK);
      sl.tocka_fe_meja[k] = m ? m : 1;
    }
    sl.fe_meja = sl.tocka_fe_meja[0];
  } else {
    sl.t_max = (int64_t)proracun;
    r->proracun_us = proracun;
    sl.inv_t_max = 64.0f / (float)sl.t_max;
    for (int k = 0; k < ST_TOCK; k++) sl.tocka_us_meja[k] = sl.t_max * (k + 1) / ST_TOCK;
    sl.fe_meja = PERIODA_URE_FE;
  }
  sl.t0 = ea_cas_us();

  int np;
  if (alg == 2) np = lshade();
  else          np = de_jde(alg == 1);

  int64_t t1 = ea_cas_us();
  r->t_zacetek_us = (uint64_t)sl.t0;
  r->t_konec_us = (uint64_t)t1;
  r->np_konec = np;
  r->fe = sl.fe;
  r->gen = sl.gen;
  r->best = sl.best;
  r->st_tock = sl.k_tocka;
}
