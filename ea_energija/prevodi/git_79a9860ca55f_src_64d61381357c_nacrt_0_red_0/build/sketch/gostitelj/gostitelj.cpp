#line 1 "/Users/aleks/gecco2027-electricity/ea_energija/gostitelj/gostitelj.cpp"
// ====================================================================
//  gostitelj.cpp - prevod ISTEGA jedra algoritmov (ea_jedro.h, tip float)
//  na računalniku, za preverjanje pravilnosti brez ESP32.
//
//  Prevod:  ./prevedi.sh
//  Zagon:   ./ea_gostitelj <alg> <funkcija> <D> <blok> <fe|cas> <proracun>
//                           [poskus=N] [ogrev] [navidezna] [sled]
//    alg: 0 = DE, 1 = jDE, 2 = L-SHADE;  funkcija: 0 = Rastrigin, 1 = Rosenbrock
//    fe <FE_max>  ali  cas <T v mikrosekundah>
//    poskus=N:  indeks poskusa (vrstica tabele POSKUSI na ESP32); vpliva na seme
//    ogrev:     ogrevalni zagon (drugo seme kot blok z isto številko)
//    navidezna: ura ni prava, ampak t = 10 us x število evalvacij (zagon v
//               načinu CAS je potem ponovljiv in neodvisen od računalnika)
//    sled:      po vsaki generaciji L-SHADE izpiše "NP <fe> <NP> <arhiv>"
//  Izpis:
//    REZ alg funkcija D blok nacin proracun fe gen best cas_us np_konec seme st_tock
//    CILJ k prag fe us            (fe = 0: cilj ni dosežen)
//    TOCKA k fe us best
//
//  Preverjanje testnih funkcij (dvojna natančnost samo tukaj, na gostitelju):
//    ./ea_gostitelj premik <funkcija> <D>       premik o, f(o), f(0), f v float in double
//    ./ea_gostitelj natancnost <funkcija> <D>   napaka float proti double blizu optimuma:
//                                               vrstice "NAT polmer povp_f najv_napaka"
//
//  Vrstni red algoritmov v bloku (pravili iz ea_jedro.h):
//    ./ea_gostitelj red nakljucni <poskus> <blok> <n>        permutacija bloka
//    ./ea_gostitelj red uravnotezen <poskus> <zagonov> <n>   permutacije vseh blokov
//
//  Preverjanje generatorja:
//    ./ea_gostitelj rng <seme> <n>              n surovih 32-bitnih izhodov
//    ./ea_gostitelj seme <poskus> <blok> <ogrev> seme zagona po pravilu seme_zagona()
//    ./ea_gostitelj meje                        največji rnd() in zgornja meja rndi(n)
//
//  To NI meritev: čas in število evalvacij na računalniku nista primerljiva
//  z ESP32. Rezultati se uporabljajo samo za teste pravilnosti algoritmov.
// ====================================================================
#include <chrono>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define SEME       20270101u
#define EA_SLED    1
#define US_NA_FE   10          // navidezna ura: mikrosekund na evalvacijo

static bool navidezna_ura = false, sled_np = false;
int64_t ea_cas_us(void);
void ea_sled_generacija(int np, int na);

#include "../ea_jedro.h"

int64_t ea_cas_us(void) {
  if (navidezna_ura) return 1000 + (int64_t)sl.fe * US_NA_FE;
  using namespace std::chrono;
  static const steady_clock::time_point t0 = steady_clock::now();
  return duration_cast<microseconds>(steady_clock::now() - t0).count();
}

void ea_sled_generacija(int np, int na) {
  if (sled_np) printf("NP %lu %d %d\n", (unsigned long)sl.fe, np, na);
}

// Ista premaknjena funkcija v DVOJNI natančnosti (referenca za E4): premik
// o so vrednosti tabele kot realna števila, brez zaokrožene vrednosti o - 1.
static double kriterij_d(const float *x) {
  double s = 0.0;
  if (FUN == 0) {
    s = 10.0 * D;
    for (int j = 0; j < D; j++) {
      double z = (double)x[j] - (double)PREMIK[j];
      s += z * z - 10.0 * cos(2.0 * M_PI * z);
    }
  } else {
    for (int j = 0; j < D - 1; j++) {
      double z0 = (double)x[j] - (double)PREMIK[j] + 1.0;
      double z1 = (double)x[j + 1] - (double)PREMIK[j + 1] + 1.0;
      double a = z1 - z0 * z0, b = 1.0 - z0;
      s += 100.0 * a * a + b * b;
    }
  }
  return s;
}

// rndi(n) z največjo možno vrednostjo generatorja (vseh 32 bitov enic)
static int rndi_najvec(int n) { return (int)((0xFFFFFFFFu >> 8) * (1.0f / 16777216.0f) * n); }

int main(int argc, char **argv) {
  if (argc == 4 && !strcmp(argv[1], "rng")) {
    rng_nastavi((uint32_t)strtoul(argv[2], NULL, 10));
    for (long i = 0, n = atol(argv[3]); i < n; i++) printf("%lu\n", (unsigned long)rnd_u32());
    return 0;
  }
  if (argc == 5 && !strcmp(argv[1], "seme")) {
    printf("%lu\n", (unsigned long)seme_zagona(SEME, atoi(argv[2]), atoi(argv[3]),
                                               atoi(argv[4]) != 0));
    return 0;
  }
  if (argc == 6 && !strcmp(argv[1], "red")) {
    int poskus = atoi(argv[3]), n = atoi(argv[5]);
    uint8_t perm[8];
    if (!strcmp(argv[2], "nakljucni")) {
      red_nakljucni(SEME, poskus, atoi(argv[4]), n, perm);
      for (int i = 0; i < n; i++) printf("%d%s", perm[i], i + 1 < n ? " " : "\n");
      return 0;
    }
    int zagonov = atoi(argv[4]);
    static uint8_t st[256];
    if (zagonov > 256 || !red_uravnotezen(SEME, poskus, zagonov, n, st)) {
      fprintf(stderr, "zagonov ni veckratnik stevila permutacij\n");
      return 1;
    }
    for (int z = 0; z < zagonov; z++) {
      permutacija_st(st[z], n, perm);
      for (int i = 0; i < n; i++) printf("%d%s", perm[i], i + 1 < n ? " " : "\n");
    }
    return 0;
  }
  if (argc == 2 && !strcmp(argv[1], "meje")) {
    float najvec = (0xFFFFFFFFu >> 8) * (1.0f / 16777216.0f);
    long slabih = 0;
    for (int n = 1; n <= 1000000; n++) slabih += rndi_najvec(n) >= n;
    printf("%.9g %d %ld\n", (double)najvec, najvec < 1.0f, slabih);
    return 0;
  }
  if (argc == 4 && (!strcmp(argv[1], "premik") || !strcmp(argv[1], "natancnost"))) {
    if (!nastavi_problem(atoi(argv[2]), atoi(argv[3])) || !alociraj()) {
      fprintf(stderr, "ni tabele premika ali premalo pomnilnika\n");
      return 1;
    }
    static float x[256];
    if (!strcmp(argv[1], "premik")) {
      for (int j = 0; j < D; j++) x[j] = PREMIK[j];
      printf("F_V_OPTIMUMU %.9e %.9e\n", (double)kriterij(x), kriterij_d(x));
      for (int j = 0; j < D; j++) x[j] = 0.0f;
      printf("F_V_SREDISCU %.9e %.9e\n", (double)kriterij(x), kriterij_d(x));
      printf("MEJE %.9g %.9g\n", (double)SPOD, (double)ZGOR);
      for (int j = 0; j < D; j++) printf("O %d %.9g\n", j, (double)PREMIK[j]);
      return 0;
    }
    const float polmeri[] = {1e-1f, 3e-2f, 1e-2f, 3e-3f, 1e-3f, 3e-4f, 1e-4f, 3e-5f};
    rng_nastavi(12345u);
    for (float r : polmeri) {
      double vsota = 0.0, najv = 0.0;
      const int n = 20000;
      for (int k = 0; k < n; k++) {
        for (int j = 0; j < D; j++) x[j] = PREMIK[j] + r * (2.0f * rnd() - 1.0f);
        double fd = kriterij_d(x), nap = fabs((double)kriterij(x) - fd);
        vsota += fd;
        if (nap > najv) najv = nap;
      }
      printf("NAT %.0e %.6e %.6e\n", (double)r, vsota / n, najv);
    }
    return 0;
  }
  if (argc < 7) {
    fprintf(stderr, "uporaba: %s <alg 0..2> <funkcija 0..1> <D> <blok> <fe|cas> <proracun> "
                    "[navidezna] [sled]\n", argv[0]);
    return 2;
  }
  int alg = atoi(argv[1]), blok = atoi(argv[4]);
  uint8_t nacin = !strcmp(argv[5], "fe") ? NACIN_FE : NACIN_CAS;
  uint64_t proracun = strtoull(argv[6], NULL, 10);
  int poskus = 0;
  bool ogrev = false;
  for (int i = 7; i < argc; i++) {
    if (!strcmp(argv[i], "navidezna")) navidezna_ura = true;
    if (!strcmp(argv[i], "sled")) sled_np = true;
    if (!strcmp(argv[i], "ogrev")) ogrev = true;
    if (!strncmp(argv[i], "poskus=", 7)) poskus = atoi(argv[i] + 7);
  }
  if (!nastavi_problem(atoi(argv[2]), atoi(argv[3]))) {
    fprintf(stderr, "ni tabele premika za to funkcijo in D\n");
    return 1;
  }
  if (!alociraj()) { fprintf(stderr, "premalo pomnilnika\n"); return 1; }
  static Rezultat r;
  pozeni((uint8_t)alg, poskus, blok, ogrev, nacin, proracun, &r);
  printf("REZ %d %d %d %d %s %" PRIu64 " %lu %lu %.9e %" PRIu64 " %u %lu %u\n", alg, FUN, D, blok,
         nacin == NACIN_FE ? "fe" : "cas", proracun, (unsigned long)r.fe, (unsigned long)r.gen,
         (double)r.best, r.t_konec_us - r.t_zacetek_us, (unsigned)r.np_konec,
         (unsigned long)r.seme, (unsigned)r.st_tock);
  for (int k = 0; k < ST_CILJEV; k++)
    printf("CILJ %d %.1e %lu %" PRIu64 "\n", k, (double)CILJI[k], (unsigned long)r.cilj_fe[k],
           r.cilj_us[k]);
  for (int k = 0; k < r.st_tock; k++)
    printf("TOCKA %d %lu %" PRIu64 " %.9e\n", k, (unsigned long)r.tocka_fe[k], r.tocka_us[k],
           (double)r.tocka_best[k]);
  sprosti();
  return 0;
}
