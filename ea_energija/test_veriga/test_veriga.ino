// ====================================================================
//  PREIZKUS VERIGE (SETUP_GUIDE.md, razdelek 4C) - kopija ea_energija.ino
//  s kratkimi nastavitvami: 1 poskus (Rastrigin D=50), 6 blokov,
//  5 s počitka, 10 s optimizacije, 1 ogrevalni zagon. ~5 min.
//  Za pravo kampanjo uporabite ea_energija.ino!
// ====================================================================
// ====================================================================
//  DE, jDE in L-SHADE na ESP32 - meritev porabe energije
//  Arduino IDE, plošča: "ESP32 Dev Module"
//
//  EN NALOG PROGRAMA = VSI POSKUSI (tabela POSKUSI spodaj, npr. Rastrigin
//  in Rosenbrock pri D = 50 in 100). Poskusi tečejo zaporedoma, brez
//  posega človeka, napaja jih samo RIGOL.
//
//  Protokol (podrobno v SETUP_GUIDE.md, razdelek 9):
//    0) ZACETNO_SPANJE_S light sleep po vklopu (ustalitev napajanja)
//    za vsak poskus (funkcija, D):
//      1) OGREVANJE zagonov vsakega algoritma - izvedejo se in zapišejo
//         kot vsi ostali, a so označeni (ogrev=1) in se ne analizirajo
//      2) ZAGONOV blokov; v vsakem bloku vsak algoritem enkrat, v
//         uravnoteženem naključnem vrstnem redu (vsaka permutacija enako
//         pogosto, zaporedje permutacij premešano s fiksnim semenom)
//      vsak zagon:  SPANJE_S light sleep (počitek + bazna poraba)
//                   OPT_S optimizacija (merilno okno, GPIO4 = 1)
//                   1 s light sleep, zapis rezultata v flash
//    nato: (WIFI_POSILJANJE 1) pošiljanje na succulent, deep sleep
//
//  Pravičnost: enak časovni proračun, enako seme za vse algoritme v
//  istem bloku (skupna naključna števila), uravnotežen vrstni red,
//  isti počitek pred vsakim zagonom, ista ploščica in nastavitve.
//
//  Branje rezultatov: prek WiFi (succulent) ali USB (zajem.py preberi).
//  Po nalaganju programa ESP32 NE začne takoj: poskus se začne ob
//  naslednjem vklopu napajanja (RIGOL, zajem.py ga vklopi sam) ali s tipko EN.
//  Nov poskus: tipka BOOT ali ukaz "n" v Serial Monitorju, ali nov program.
// ====================================================================
#include "esp_sleep.h"
#include <Preferences.h>
#include <LittleFS.h>
#include <algorithm>

// ======================= NASTAVITVE POSKUSA =========================
#define ZAGONOV    6     // blokov = ponovitev VSAKEGA algoritma (večkratnik 6!)
#define SPANJE_S   5     // počitek (light sleep) pred vsako optimizacijo (s)
#define OPT_S      10     // trajanje ene optimizacije (s)
#define OGREVANJE  1      // ogrevalnih zagonov vsakega algoritma na poskus
#define ZACETNO_SPANJE_S 10   // spanje takoj po vklopu, pred vsem ostalim (s)
#define SEME       20270101u  // osnovno seme (zapiše se v izpis)

// Poskusi, ki se izvedejo zaporedoma: {funkcija, D}
// funkcija: 0 = Rastrigin, 1 = Rosenbrock;  D: do DMAX
struct Nastavitev { uint8_t funkcija; uint8_t D; };
const Nastavitev POSKUSI[] = {{0, 50}};
#define DMAX       100

// Kateri algoritmi se primerjajo: 0 = klasični DE, 1 = jDE, 2 = L-SHADE
const uint8_t ALGORITMI[] = {0, 1, 2};

// Cilj za "energijo do cilja": prvi trenutek, ko je best <= PRAG_CILJA.
#define PRAG_CILJA 1e-6f

// Število točk konvergenčne krivulje (best ob t = OPT_S*k/TOCK, k=1..TOCK)
#define TOCK       20

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
// Originalno je NP_init = 18*D. To pri D = 50 pomeni 900 posameznikov
// in s 2,6-kratnim arhivom ~830 kB RAM, česar ESP32 nima (~300 kB).
// Zato NP_init omejimo tako, da pomnilnik ostane pod ~170 kB.
// To odstopanje od originala navedite v članku!
// (makro, ker Arduino IDE prototipe funkcij vstavi pred prvo funkcijo)
#define ls_np_init(d) ((18 * (d) < 9200 / (d)) ? 18 * (d) : 9200 / (d))
#define LS_NP_MIN   4
#define LS_H        6       // velikost zgodovinskega spomina
#define LS_P        0.11f   // delež najboljših za current-to-pbest
#define LS_RARC     2.6f    // velikost arhiva = LS_RARC * NP

// ---- strojna oprema ----
#define MARKER     4      // GPIO, ki je 1 med optimizacijo (za osciloskop)
#define TIPKA_BOOT 0      // tipka BOOT na ploščici (GPIO0)

// 1 = med poskusom izpisuj napredek na UART (samo za preizkus prek USB!)
// 0 = med poskusom popolnoma tiho (za pravo meritev z RIGOL-om)
#define IZPIS_MED_POSKUSOM 0

// 1 = po ZADNJEM zagonu rezultate pošlji prek WiFi na strežnik succulent
//     (podatki o omrežju in strežniku so v wifi_nastavitve.h).
//     WiFi se med meritvijo NIKOLI ne vklopi: ESP32 se po zadnjem zagonu
//     znova zažene (deep sleep 2 s), pošlje rezultate in gre v deep sleep.
//     Tokovno omejitev RIGOL-a takrat nastavite na 500 mA.
// 0 = brez WiFi, rezultate preberete prek USB (zajem.py preberi)
#define WIFI_POSILJANJE 0
// ====================================================================

#if WIFI_POSILJANJE
#include <WiFi.h>
#include <HTTPClient.h>
#include "wifi_nastavitve.h"     // kopija wifi_nastavitve_primer.h s podatki
#endif

#define N_ALG    (sizeof(ALGORITMI) / sizeof(ALGORITMI[0]))
#define N_POSK   (sizeof(POSKUSI) / sizeof(POSKUSI[0]))
#define PI_F     3.14159265f
const char *IME_ALG[] = {"DE", "jDE", "LSHADE"};
const char *IME_FUN[] = {"rastrigin", "rosenbrock"};

// ======================= SHRANJEVANJE V FLASH =======================
// Stanje hranimo v NVS (Preferences), rezultate pa zaporedno v datoteki
// /rez.bin na LittleFS. Oboje preživi izklop napajanja.
#define DATOTEKA "/rez.bin"
#define STANJE_TECE    1   // poskus se izvaja (ali je bil prekinjen)
#define STANJE_KONCAN  2   // vsi zagoni so končani
#define STANJE_NAPAKA  3   // premalo pomnilnika
#define STANJE_PRIPRAVLJEN 4   // nov program naložen, poskus se začne ob naslednjem vklopu

struct Rezultat {          // en zagon enega algoritma
  uint8_t  alg;            // 0 = DE, 1 = jDE, 2 = L-SHADE
  uint8_t  zagon;          // številka bloka (ponovitve); ogrevanje: 0..OGREVANJE-1
  uint8_t  poskus;         // indeks v POSKUSI
  uint8_t  poz;            // položaj algoritma v bloku (0 = prvi)
  uint8_t  ogrev;          // 1 = ogrevalni zagon (ne analizira se)
  uint8_t  rezerva;
  uint16_t np_konec;       // velikost populacije ob koncu (L-SHADE jo manjša)
  uint32_t fe;             // število evalvacij
  uint32_t gen;            // število generacij
  uint32_t cas_ms;         // dejanski čas optimizacije
  uint32_t fe_cilj;        // evalvacij do best <= PRAG_CILJA (0 = ni doseženo)
  uint32_t ms_cilj;        // milisekund do cilja (0 = ni doseženo)
  float    best;           // najboljša najdena vrednost
  float    konv[TOCK];     // best ob t = OPT_S*k/TOCK
};
Rezultat rez;              // trenutni zagon (vsi so v flashu, ne v RAM-u)
Preferences flash;

// Oznaka prevoda: ob vsakem novem nalaganju je drugačna,
// zato se stari rezultati samodejno pobrišejo.
const char *OZNAKA_PREVODA = __DATE__ " " __TIME__;

// ======================= TRENUTNI POSKUS ============================
int   D;                   // dimenzija
int   FUN;                 // 0 = Rastrigin, 1 = Rosenbrock
float SPOD, ZGOR;          // meje iskalnega prostora
int   LS_NP_INIT;          // začetna populacija L-SHADE pri tem D
int   NP_MAX, ARH_MAX;     // velikosti alociranih tabel

void nastavi_poskus(int e) {
  FUN = POSKUSI[e].funkcija;
  D = POSKUSI[e].D;
  SPOD = (FUN == 0) ? -5.12f : -30.0f;
  ZGOR = (FUN == 0) ?  5.12f :  30.0f;
  LS_NP_INIT = ls_np_init(D);
  NP_MAX = std::max(std::max(DE_NP, JDE_NP), LS_NP_INIT);
  ARH_MAX = (int)(LS_RARC * LS_NP_INIT) + 1;
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
  free(idx); free(SF); free(SCR); free(Sdf);
  X = U = A = NULL;
  fx = fu = Fpar = CRpar = Ftr = CRtr = SF = SCR = Sdf = NULL;
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
  return fx && fu && Fpar && CRpar && Ftr && CRtr && idx && SF && SCR && Sdf;
}

// ======================= NAKLJUČNA ŠTEVILA ==========================
// xorshift32: preprost, hiter, isto seme = isti rezultat.
uint32_t rng;
inline float rnd() {                   // enakomerno v [0, 1)
  rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
  return (rng >> 8) * (1.0f / 16777216.0f);
}
inline int rndi(int n) { return (int)(rnd() * n); }   // celo v [0, n)

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
// Obe imata globalni minimum 0. Vse v float (ESP32 ima FPU samo za float).
float kriterij(const float *x) {
  float s = 0.0f;
  if (FUN == 0) {                      // Rastrigin, meje [-5.12, 5.12]
    s = 10.0f * D;
    for (int j = 0; j < D; j++)
      s += x[j] * x[j] - 10.0f * cosf(2.0f * PI_F * x[j]);
  } else {                             // Rosenbrock, meje [-30, 30]
    for (int j = 0; j < D - 1; j++) {
      float a = x[j + 1] - x[j] * x[j];
      float b = 1.0f - x[j];
      s += 100.0f * a * a + b * b;
    }
  }
  return s;
}

// ======================= SPREMLJANJE ZAGONA =========================
// Skupno za vse algoritme: štetje evalvacij, najboljša vrednost,
// trenutek dosega cilja in točke konvergenčne krivulje.
struct Sledenje {
  uint32_t t0, fe, fe_cilj, us_cilj;
  float best;
  int k;                               // naslednja točka konvergence
} sl;
Rezultat *trenutni;

inline float oceni(const float *x) {
  float f = kriterij(x);
  sl.fe++;
  if (f < sl.best) {
    sl.best = f;
    // Prvi doseg cilja si zapomnimo (micros kličemo le enkrat).
    if (sl.fe_cilj == 0 && f <= PRAG_CILJA) {
      sl.fe_cilj = sl.fe;
      sl.us_cilj = micros() - sl.t0;
    }
  }
  return f;
}

// Pokliče se enkrat na generacijo. Zabeleži točke konvergence in
// vrne true, ko je čas potekel. Vrne tudi pretečeni delež časa.
bool konec_casa(float *delez) {
  uint32_t t = micros() - sl.t0;
  while (sl.k < TOCK && t >= (uint64_t)OPT_S * 1000000ULL * (sl.k + 1) / TOCK) {
    trenutni->konv[sl.k++] = sl.best;
  }
  if (delez) *delez = t / (OPT_S * 1e6f);
  return t >= OPT_S * 1000000UL;
}

inline void zamenjaj(float **a, float **b) { float *t = *a; *a = *b; *b = t; }

// Inicializacija populacije velikosti n (enakomerno v mejah)
void inicializiraj(int n) {
  for (int i = 0; i < n; i++) {
    for (int j = 0; j < D; j++) X[i][j] = SPOD + rnd() * (ZGOR - SPOD);
    fx[i] = oceni(X[i]);
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
  for (int i = 0; i < NP; i++) { Fpar[i] = 0.5f; CRpar[i] = 0.9f; }

  uint32_t gen = 0;
  while (!konec_casa(NULL)) {
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
    }
    // selekcija: boljši ali enak poskusni vektor zamenja starša
    for (int i = 0; i < NP; i++) {
      if (fu[i] <= fx[i]) {
        zamenjaj(&X[i], &U[i]);
        fx[i] = fu[i];
        if (jde) { Fpar[i] = Ftr[i]; CRpar[i] = CRtr[i]; }   // parametra preživita
      }
    }
    gen++;
  }
  trenutni->gen = gen;
  return NP;
}

// ======================= L-SHADE ====================================
// Tanabe & Fukunaga, "Improving the search performance of SHADE using
// linear population size reduction", IEEE CEC 2014.
//  - mutacija current-to-pbest/1 z arhivom,
//  - zgodovinski spomin M_F, M_CR velikosti H,
//  - F ~ Cauchy(M_F, 0.1), CR ~ N(M_CR, 0.1),
//  - posodobitev spomina z uteženo Lehmerjevo sredino,
//  - linearno zmanjševanje populacije (LPSR) od NP_init do NP_min.
// RAZLIKA OD ORIGINALA: LPSR je vezan na pretečeni ČAS namesto na
// število evalvacij, ker je zaustavitveni pogoj čas (in ne MAX_NFE).
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
  int k = 0, nA = 0;
  uint32_t gen = 0;
  float delez;

  while (!konec_casa(&delez)) {
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

    // --- linearno zmanjševanje populacije (glede na pretečeni čas) ---
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
    gen++;
  }
  trenutni->gen = gen;
  return NP;
}

// ======================= EN ZAGON ===================================
// Seme je odvisno samo od poskusa in bloka, zato vsi algoritmi v istem
// bloku dobijo isto zaporedje naključnih števil (skupna naključna števila).
void pozeni(uint8_t alg, int poskus, int zagon, bool ogrev, Rezultat *r) {
  memset(r, 0, sizeof(*r));
  r->alg = alg; r->zagon = zagon; r->poskus = poskus; r->ogrev = ogrev;
  trenutni = r;
  rng = SEME + 7919u * zagon + 104729u * poskus + (ogrev ? 0x5bd1e995u : 0u);
  if (rng == 0) rng = 1;
  for (int i = 0; i < 20; i++) rnd();  // "ogrevanje" generatorja

  sl.fe = 0; sl.fe_cilj = 0; sl.us_cilj = 0; sl.best = 1e30f; sl.k = 0;
  sl.t0 = micros();

  int np;
  if (alg == 2) np = lshade();
  else          np = de_jde(alg == 1);

  uint32_t t = micros() - sl.t0;
  while (sl.k < TOCK) r->konv[sl.k++] = sl.best;   // za vsak slučaj
  r->np_konec = np;
  r->fe = sl.fe;
  r->cas_ms = t / 1000;
  r->best = sl.best;
  r->fe_cilj = sl.fe_cilj;
  r->ms_cilj = sl.fe_cilj ? (sl.us_cilj + 500) / 1000 : 0;
  if (r->fe_cilj && r->ms_cilj == 0) r->ms_cilj = 1;   // 0 pomeni "ni doseženo"
}

// ======================= VRSTNI RED ZAGONOV =========================
// Uravnotežen naključni vrstni red: vsaka permutacija algoritmov se
// pojavi enako pogosto (če je ZAGONOV večkratnik N_ALG!), zaporedje
// permutacij pa je premešano s fiksnim semenom. Tako je vsak algoritem
// enako pogosto prvi, drugi, ... in enako pogosto sledi vsakemu drugemu
// (izničimo vpliv položaja, segrevanja in prenosa iz prejšnjega zagona).
#define MAX_PERM 24        // do 4 algoritmi
uint8_t permutacije[MAX_PERM][N_ALG];
int n_perm = 0;
uint8_t blok_perm[ZAGONOV];

void pripravi_vrstni_red(int poskus) {
  uint8_t p[N_ALG];
  for (int a = 0; a < (int)N_ALG; a++) p[a] = a;
  n_perm = 0;
  do {
    memcpy(permutacije[n_perm++], p, N_ALG);
  } while (n_perm < MAX_PERM && std::next_permutation(p, p + N_ALG));
  for (int z = 0; z < ZAGONOV; z++) blok_perm[z] = z % n_perm;
  uint32_t s = SEME ^ (0x9E3779B9u * (poskus + 1));   // ločen generator
  for (int z = ZAGONOV - 1; z > 0; z--) {             // Fisher-Yates
    s ^= s << 13; s ^= s >> 17; s ^= s << 5;
    int j = s % (z + 1);
    std::swap(blok_perm[z], blok_perm[j]);
  }
}

// ======================= POSKUS (napajanje z RIGOL-a) ===============
void spi(uint64_t us) {
  esp_sleep_enable_timer_wakeup(us);
  esp_light_sleep_start();
}

// En korak protokola: počitek, merilno okno, počitek, zapis v flash.
void korak(uint8_t alg, int poskus, int zagon, int poz, bool ogrev) {
  spi((uint64_t)SPANJE_S * 1000000ULL);       // počitek + bazna poraba

  digitalWrite(MARKER, HIGH);                 // ---- merilno okno ----
  pozeni(alg, poskus, zagon, ogrev, &rez);
  digitalWrite(MARKER, LOW);                  // ---------------------
  rez.poz = poz;

  spi(1000000ULL);                            // loči optimizacijo od pisanja
  File f = LittleFS.open(DATOTEKA, FILE_APPEND);
  f.write((const uint8_t *)&rez, sizeof(Rezultat));
  f.close();
#if IZPIS_MED_POSKUSOM
  Serial.printf("#%s %s D=%d %s blok %d poz %d best=%.3e fe=%lu\n",
                ogrev ? "OGREV" : "ZAGON", IME_FUN[FUN], D, IME_ALG[alg], zagon, poz,
                (double)rez.best, (unsigned long)rez.fe);
  Serial.flush();
#endif
}

void izvedi_poskus() {
  // Po vklopu najprej mirujemo, da se napajanje ustali.
  spi((uint64_t)ZACETNO_SPANJE_S * 1000000ULL);
  flash.putUChar("stanje", STANJE_TECE);
  // Števec zagonov ESP32 med poskusom: > 1 pomeni, da se je vmes
  // resetiral (npr. padec napetosti) in je poskus začel znova.
  flash.putUChar("resetov", flash.getUChar("resetov", 0) + 1);
  // Ob prvem zagonu po nalaganju se LittleFS formatira (lahko traja
  // nekaj sekund), zato je to tu, pred prvim zagonom.
  LittleFS.begin(true);
  LittleFS.remove(DATOTEKA);           // stari rezultati se pobrišejo

#if IZPIS_MED_POSKUSOM
  Serial.begin(115200);
  delay(500);
#else
  // TX pin v visoko impedanco, da ESP32 ne napaja USB-UART čipa
  // na ploščici prek podatkovne linije.
  pinMode(1, INPUT);
#endif

  for (int e = 0; e < (int)N_POSK; e++) {
    nastavi_poskus(e);
    if (!alociraj()) {                 // premalo pomnilnika (prevelik D)
      flash.putUChar("stanje", STANJE_NAPAKA);
      flash.putUChar("napaka_e", e);
      flash.end();
      esp_deep_sleep_start();
    }
#if IZPIS_MED_POSKUSOM
    Serial.printf("#Poskus %d: %s D=%d, prosti RAM: %u B\n", e, IME_FUN[FUN], D,
                  ESP.getFreeHeap());
#endif
    pripravi_vrstni_red(e);
    // 1) ogrevanje: vsak algoritem OGREVANJE-krat (rezultati se zavržejo)
    for (int w = 0; w < OGREVANJE; w++)
      for (int a = 0; a < (int)N_ALG; a++)
        korak(ALGORITMI[a], e, w, a, true);
    // 2) meritve: bloki z uravnoteženim naključnim vrstnim redom
    for (int z = 0; z < ZAGONOV; z++) {
      const uint8_t *perm = permutacije[blok_perm[z]];
      for (int poz = 0; poz < (int)N_ALG; poz++)
        korak(ALGORITMI[perm[poz]], e, z, poz, false);
    }
    sprosti();
  }
  flash.putUChar("stanje", STANJE_KONCAN);
#if WIFI_POSILJANJE
  // Merjenje je končano. Za WiFi potrebujemo ~50 kB RAM, zato ESP32
  // znova zaženemo (deep sleep 2 s = reset) in rezultate pošljemo ob
  // novem zagonu s čistim pomnilnikom.
  flash.putUChar("poslji", 1);
  flash.putUChar("wifi_posk", 0);
  flash.end();
  esp_sleep_enable_timer_wakeup(2000000ULL);
#else
  flash.end();
#endif
  esp_deep_sleep_start();              // konec: tok pade skoraj na nič
}

// ======================= BRANJE IN IZPIS REZULTATOV =================
int st_rezultatov() {
  LittleFS.begin(true);
  File f = LittleFS.open(DATOTEKA, FILE_READ);
  if (!f) return 0;
  int n = f.size() / sizeof(Rezultat);
  f.close();
  return n;
}

bool beri_rezultat(int i, Rezultat *r) {
  File f = LittleFS.open(DATOTEKA, FILE_READ);
  if (!f) return false;
  bool ok = f.seek(i * sizeof(Rezultat)) &&
            f.read((uint8_t *)r, sizeof(Rezultat)) == sizeof(Rezultat);
  f.close();
  return ok;
}

void izpisi_glavo(Print &o) {
  o.printf("\n#POSKUS zagonov=%d spanje=%ds opt=%ds ogrevanje=%d tock=%d cilj=%.3e "
           "seme=%lu DE_NP=%d JDE_NP=%d resetov=%u prevod=%s poskusi=",
           ZAGONOV, SPANJE_S, OPT_S, OGREVANJE, TOCK, (double)PRAG_CILJA,
           (unsigned long)SEME, DE_NP, JDE_NP, flash.getUChar("resetov", 0),
           OZNAKA_PREVODA);
  for (int e = 0; e < (int)N_POSK; e++)
    o.printf("%s%s/%d", e ? ";" : "", IME_FUN[POSKUSI[e].funkcija], POSKUSI[e].D);
  o.println();
}

void izpisi_vse(int n) {
  izpisi_glavo(Serial);
  Serial.println("#REZ,i,poskus,funkcija,D,alg,zagon,poz,ogrev,fe,gen,best,"
                 "cas_ms,fe_cilj,ms_cilj,np_konec,LS_NP_INIT");
  Rezultat r;
  for (int i = 0; i < n; i++) {
    if (!beri_rezultat(i, &r)) break;
    const Nastavitev &p = POSKUSI[r.poskus];
    Serial.printf("REZ,%d,%u,%s,%u,%s,%u,%u,%u,%lu,%lu,%.6e,%lu,%lu,%lu,%u,%d\n", i,
                  r.poskus, IME_FUN[p.funkcija], p.D, IME_ALG[r.alg], r.zagon, r.poz,
                  r.ogrev, (unsigned long)r.fe, (unsigned long)r.gen, (double)r.best,
                  (unsigned long)r.cas_ms, (unsigned long)r.fe_cilj,
                  (unsigned long)r.ms_cilj, r.np_konec, ls_np_init(p.D));
  }
  Serial.println("#KONV,i,alg,zagon,best_1 ... best_TOCK");
  for (int i = 0; i < n; i++) {
    if (!beri_rezultat(i, &r)) break;
    Serial.printf("KONV,%d,%s,%u", i, IME_ALG[r.alg], r.zagon);
    for (int k = 0; k < TOCK; k++) Serial.printf(",%.4e", (double)r.konv[k]);
    Serial.println();
  }
  Serial.println("#KONEC_IZPISA   (BOOT ali 'n' = pobriši in začni nov poskus)");
}

// ======================= POŠILJANJE PREK WIFI (succulent) ===========
#if WIFI_POSILJANJE
#define WIFI_ROK_MS        (30000 + 150 * N_POSK * N_ALG * (ZAGONOV + OGREVANJE))
#define WIFI_MAX_POSKUSOV  3       // samodejni poskusi po koncu poskusa

// En zapis kot JSON objekt. Imena polj se morajo ujemati s stolpci
// v configuration.yml strežnika succulent.
int v_json(char *buf, size_t vel, int i, const Rezultat &r, const char *mac) {
  const Nastavitev &p = POSKUSI[r.poskus];
  int m = snprintf(buf, vel,
    "{\"prevod\":\"%s\",\"mac\":\"%s\",\"zagonov\":%d,\"spanje\":%d,\"opt\":%d,"
    "\"ogrevanje\":%d,\"tock\":%d,\"cilj\":%.3e,\"seme\":%lu,\"resetov\":%u,"
    "\"i\":%d,\"poskus\":%u,\"funkcija\":\"%s\",\"D\":%u,\"alg\":\"%s\","
    "\"zagon\":%u,\"poz\":%u,\"ogrev\":%u,\"fe\":%lu,\"gen\":%lu,\"best\":%.6e,"
    "\"cas_ms\":%lu,\"fe_cilj\":%lu,\"ms_cilj\":%lu,\"np_konec\":%u,"
    "\"LS_NP_INIT\":%d,\"konv\":\"",
    OZNAKA_PREVODA, mac, ZAGONOV, SPANJE_S, OPT_S, OGREVANJE, TOCK,
    (double)PRAG_CILJA, (unsigned long)SEME, flash.getUChar("resetov", 0),
    i, r.poskus, IME_FUN[p.funkcija], p.D, IME_ALG[r.alg], r.zagon, r.poz, r.ogrev,
    (unsigned long)r.fe, (unsigned long)r.gen, (double)r.best,
    (unsigned long)r.cas_ms, (unsigned long)r.fe_cilj, (unsigned long)r.ms_cilj,
    r.np_konec, ls_np_init(p.D));
  for (int k = 0; k < TOCK && m < (int)vel; k++)
    m += snprintf(buf + m, vel - m, k ? ";%.4e" : "%.4e", (double)r.konv[k]);
  if (m < (int)vel) m += snprintf(buf + m, vel - m, "\"}");
  return m;
}

// Pošlje n zapisov na SUCC_URL. Vrne true, če je strežnik sprejel vse.
// log = &Serial za izpis (prek USB), NULL med delovanjem na RIGOL-u.
bool poslji_wifi(int n, Print *log) {
  uint32_t t0 = millis();
  WiFi.persistent(false);              // ne piši podatkov omrežja v flash
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                // hitrejši prenos; v toku jasno višja moč kot računanje
  WiFi.begin(WIFI_SSID, WIFI_GESLO);
  WiFi.setTxPower(WIFI_MOC_ODDAJANJA);  // nižja moč = nižje tokovne konice
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(100);
  bool ok = WiFi.status() == WL_CONNECTED;
  if (log) log->printf(ok ? "#WiFi povezan, IP %s\n" : "#WiFi: povezava ni uspela (%s)\n",
                       ok ? WiFi.localIP().toString().c_str() : WIFI_SSID);
  String mac = WiFi.macAddress();
  static char telo[700 + 16 * TOCK];
  Rezultat r;
  HTTPClient http;
  for (int i = 0; ok && i < n; i++) {
    if (millis() - t0 > (uint32_t)WIFI_ROK_MS) { ok = false; break; }
    if (!beri_rezultat(i, &r)) { ok = false; break; }
    v_json(telo, sizeof(telo), i, r, mac.c_str());
    int koda = -1;
    for (int p = 0; p < 3 && koda != 200; p++) {      // do 3 poskusi na zapis
      http.begin(SUCC_URL);
      http.setConnectTimeout(3000);
      http.setTimeout(3000);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("Authorization", "Bearer " SUCC_GESLO);
      koda = http.POST((uint8_t *)telo, strlen(telo));
      http.end();
    }
    if (koda != 200) ok = false;
    if (log) log->printf("#WiFi zapis %d/%d: HTTP %d\n", i + 1, n, koda);
  }
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  if (log) log->printf(ok ? "#WiFi: poslanih %d zapisov\n" : "#WiFi: pošiljanje ni uspelo\n", n);
  return ok;
}

// Prvi zagon po koncu poskusa (še na RIGOL-u): pošlji in zaspi.
// Ob neuspehu (npr. reset zaradi padca napetosti) poskusi znova do
// WIFI_MAX_POSKUSOV-krat, nato obupa. Rezultati ostanejo v flashu.
void posiljanje_po_poskusu() {
  uint8_t posk = flash.getUChar("wifi_posk", 0);
  flash.putUChar("wifi_posk", posk + 1);   // šteje tudi, če se vmes resetira
  bool ok = poslji_wifi(st_rezultatov(), NULL);
  if (ok || posk + 1 >= WIFI_MAX_POSKUSOV) {
    flash.putUChar("poslji", 0);
    flash.putUChar("poslano", ok);
  } else {
    esp_sleep_enable_timer_wakeup(5000000ULL);   // čez 5 s poskusi znova
  }
  flash.end();
  esp_deep_sleep_start();
}
#endif

// ======================= IZPIS (napajanje prek USB) =================
void izpisuj_rezultate(bool napaka) {
  Serial.begin(115200);
  int n = st_rezultatov();
  pinMode(TIPKA_BOOT, INPUT_PULLUP);

  while (true) {
    if (napaka) {
      int e = flash.getUChar("napaka_e", 0);
      Serial.printf("\n#NAPAKA: premalo pomnilnika za poskus %d (%s, D=%d). "
                    "Zmanjšajte D ali NP. Uspešnih zapisov: %d\n",
                    e, IME_FUN[POSKUSI[e].funkcija], POSKUSI[e].D, n);
    } else {
      izpisi_vse(n);
    }
    for (int k = 0; k < 1000; k++) {   // 10 s čakamo na BOOT ali "n"
      bool tipka = digitalRead(TIPKA_BOOT) == LOW;
      int znak   = Serial.available() ? Serial.read() : -1;
      bool ukaz  = znak == 'n';
#if WIFI_POSILJANJE
      if (znak == 'w' && !napaka) {    // ročno (ponovno) pošiljanje prek WiFi
        Serial.println("#Pošiljam rezultate prek WiFi ...");
        poslji_wifi(n, &Serial);
      }
#endif
      if (tipka || ukaz) {
        Serial.println("#Rezultati pobrisani, začenjam nov poskus ...");
        Serial.flush();
        LittleFS.remove(DATOTEKA);
        flash.putUChar("stanje", STANJE_PRIPRAVLJEN);
        flash.putUChar("resetov", 0);
        flash.end();
        Serial.println("#Poskus se začne ob naslednjem vklopu (RIGOL) ali s tipko EN.");
        Serial.flush();
        esp_deep_sleep_start();
      }
      delay(10);
    }
  }
}

// ======================= GLAVNI PROGRAM =============================
void setup() {
  pinMode(MARKER, OUTPUT);
  digitalWrite(MARKER, LOW);
  setCpuFrequencyMhz(240);             // fiksna frekvenca za vse zagone
  disableCore1WDT();                   // watchdog ne sme motiti računanja

  flash.begin("ea", false);
  if (flash.getString("prevod", "") != String(OZNAKA_PREVODA)) {
    // Nov program: stari rezultati so neveljavni. Poskusa NE začnemo
    // takoj (ESP32 je še na USB), ampak ob naslednjem vklopu z RIGOL-om.
    flash.clear();
    flash.putString("prevod", OZNAKA_PREVODA);
    flash.putUChar("stanje", STANJE_PRIPRAVLJEN);
    LittleFS.begin(true);              // formatiranje ob prvem zagonu, še na USB
    LittleFS.remove(DATOTEKA);
    Serial.begin(115200);
    delay(300);
    Serial.println("\n#PRIPRAVLJEN: program naložen. Odklopite USB; poskus se začne "
                   "ob naslednjem vklopu napajanja (RIGOL) ali s tipko EN.");
    Serial.flush();
    flash.end();
    esp_deep_sleep_start();            // brez bujenja: čaka na izklop/vklop ali EN
  }

  uint8_t stanje = flash.getUChar("stanje", 0);
  if (stanje == STANJE_KONCAN) {
#if WIFI_POSILJANJE
    if (flash.getUChar("poslji", 0)) posiljanje_po_poskusu();   // se ne vrne
#endif
    izpisuj_rezultate(false);
  }
  else if (stanje == STANJE_NAPAKA) izpisuj_rezultate(true);
  else izvedi_poskus();
}

void loop() {}                         // ne uporabljamo
