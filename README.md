# OSC2 → CARLA Compiler

ASAM OpenSCENARIO 2.1 DSL'ini CARLA simülatöründe çalışan py_trees davranış ağaçlarına çeviren, makale tabanlı bir derleyici reprodüksiyonu.

- Makale: *Compiling OpenSCENARIO 2.1 for Scenario-Based Testing in CARLA* (arXiv:2604.16452)
- Durum: Aşama 0 (ortam), Aşama 1 (lexer/parser/AST), Aşama 2 (semantik), Aşama 3 (runtime + BT), Aşama 4 (CARLA adaptörü + cut-in), Aşama 5 (doğrulama + ölçüm) ve Aşama 5.7 (kullanıcı tanımlı modifier genişletme) tamam.
- Hedef: 31 Ocak 2027'ye kadar tez (Aşama 6).

## Hızlı başlangıç

```bash
cd C:\Users\canke\Desktop\osc2-carla
.venv\Scripts\activate
pip install -e .
pytest -q
osc2c ast scenarios/dev/smoke4.osc
osc2c check scenarios/dev/smoke4.osc
osc2c bt scenarios/dev/stage3_sync.osc
osc2c run scenarios/dev/stage3_sync.osc --ticks 200 --trace

# CARLA sunucusu açıkken gerçek simülatörde cut-in
osc2c run scenarios/carla/cut_in.osc --carla --map Town10HD_Opt --spawn-index 20 --ticks 300 --trace
pytest -m carla -q

# doğrulama ve ölçüm (CARLA'sız)
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 \
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md
python tools/coverage.py --markdown docs/measurements/coverage.md
```

`osc2c check` sembol tablosunu, tipleri ve birimleri çözer; hataları kararlı kodlarla
(`E0401`, `E0301`, ...) raporlar. `--strict` uyarıları da hataya çevirir,
`--dump-symbols` sembol tablosunu JSON olarak döker, `--stdlib FILE` harici ASAM
tip dosyalarını yükler.

`osc2c bt` derlenmiş davranış ağacını JSON olarak verir. `osc2c run` aynı ağacı
deterministik `MockAdapter` üzerinde çalıştırır; olayları ve aktör durumunu raporlar.

ASAM 2.2.0 paketi (`grammar.ebnf`, `types.osc`, `domain.osc`, `standard.osc`)
`external/asam/` altında yerel olarak durur ve `.gitignore` kapsamındadır.
`--stdlib external/asam/standard.osc` gerçek kütüphaneyi import zinciriyle
yükler; verilmezse `semantics/stdlib.py` içindeki yerleşik `stdtypes` / `std`
alt kümesi kullanılır. Gerçek kütüphaneye bağlı testler dosyalar yoksa atlanır.

## Davranış ağacı eşlemesi

| OSC2 | py_trees | Not |
| --- | --- | --- |
| `serial` | `Sequence(memory=True)` | sıralı; başarılı çocuk yeniden çalışmaz |
| `parallel` | `Parallel(SuccessOnAll)` | tüm dallar bitince başarılı |
| `one_of` | `Parallel(SuccessOnOne)` | koşan dalı aç bırakmamak için Selector değil |
| `drive` / `walk` | süreli yaprak | hedef hızı her tick uygular, `RUNNING` kalır |
| `wait elapsed/rise/fall/@event` | koşul yaprağı | `rise`/`fall` gerçek kenar algılar |
| `emit` | blackboard olayı | olaylar kalıcıdır (latched) |

Süreli `drive` bir `serial` içinde tek başına bitmez; `one_of` veya bir `wait` ile
sonlandırılması gerekir. Bu, makaledeki Listing 2'nin faz yapısıyla aynıdır.

Kullanıcı tanımlı modifier'lar derleme zamanında standart uygulamalara
düzleştirilir: `modifier fast of vehicle: speed(10 mps)` tanımı,
`hero.drive() with: fast()` çağrısında `speed(10 mps)` gibi davranır. Aynı
genişletme nitelikli eylem gövdelerine ve `at: start` yükseltmesine uygulanır;
kaynak sırası korunur, döngü ve desteklenmeyen gövde üyeleri uyarıyla
raporlanır (`src/osc2c/backend/modifiers.py`).

## CARLA üzerinde çalıştırma

`--carla` verilmediği sürece her şey `MockAdapter` üzerinde, CARLA sunucusu olmadan
çalışır. Gerçek simülatörde:

- Adaptör synchronous mode'u ve sabit `fixed_delta_seconds` değerini açar; kapanırken
  önceki settings/weather değerlerini geri yükler ve oluşturduğu aktörleri yok eder.
- Aktörler `role_name` ile eşlenir; harita spawn noktaları, aynı yönde uzun bir sol
  şerit görüşüne göre sıralanır ve `--spawn-index` bu sıralamada başlangıç noktasını
  seçer (dolu spawn noktaları atlanır).
- `assign_position` göreli `ahead_of`/`behind` + `distance` ve `lane(side_of:)`
  kombinasyonlarını destekler. `at: start` aksiyonları derleme sırasında bir kez
  uygulanır; ağaçta bunların yerine başarılı bir yaprak durur.
- `change_lane`, hedef şerit kimliği ve şerit merkezine yaklaşma (0.7 m) birlikte
  sağlanınca tamamlanır; yol kimliği kavşaklarda değiştiği için tek başına
  kullanılmaz.
- Desteklenen araç blueprint'leri `tesla.model3` ve `lincoln.mkz_2017`; harita
  varsayılanı sunucunun mevcut haritasıdır.

`scenarios/carla/cut_in.osc` hero'yu 12 m/s sabit hızla sürerken sol şeritteki NPC'yi
2 s sonra sağa şerit değiştirmeye zorlar; `CUT_IN` olayından sonra hero frenler.
Mock'ta 41 tick (4.0 s) sürer; CARLA'da geometrik olarak doğrulanır
(`tests/test_carla.py`).

## Doğrulama ve ölçüm

`docs/VALIDATION.md`, beş senaryonun mock sonuçlarını, 20 tekrarlı determinizm
testlerini, derleme/tick gecikmelerini, CARLA cut-in KPI'larını ve makale
Table 2 için hazırlanan kapsam matrisini içerir. Ham veriler
`docs/measurements/` altındadır.

- **Determinizm:** aynı senaryo, aynı ayarlar ve aynı adımla tick-by-tick
  aktör durumu aynı SHA-256 trace hash'ini üretir. Mock'ta 5/5 senaryo
  bit düzeyinde deterministik. CARLA'da davranış ve geometri 20/20 tekrarlı
  koşuda aynı; trace hash'i çoğu oturumda tek olsa da fizik gürültüsü
  (ör. 6×10⁻⁶ m/s hız farkı) hash'i değiştirebilir, bu yüzden CARLA için
  "her zaman aynı hash" iddia edilmez.
- **Kapsam:** 43 yetenek satırı → 24 desteklenen, 10 kısmi, 9 desteklenmeyen
  (katı %56, ağırlıklı %67). Her satır çalışan bir kanıt dosyasına bağlıdır.
- **Maliyet:** CARLA'da tick medyanı 5.45 ms; derleyicisiz baseline'ın tam
  döngüsü 5.38 ms. Derleme steady-state ~130 ms (parser ağırlıklı).

`tools/bench.py` mock/CARLA ölçümlerini, `tools/coverage.py` kapsam matrisini,
`tools/baseline_carla.py` ise derleyicisiz kontrol grubunu çalıştırır.

## Yapı

```text
grammar/                     OSC 2.1 ANTLR grammar (MPL-2.0 türevi)
tools/                       ANTLR 4.13.2 jar
src/osc2c/frontend/          parser, AST, transformer
src/osc2c/semantics/         sembol tablosu, tipler, birimler
src/osc2c/backend/           BT üretimi, MethodRegistry
src/osc2c/runtime/           ExecutionContext, olaylar, atomik davranışlar
src/osc2c/adapters/          SimAdapter, CarlaAdapter, MockAdapter
src/osc2c/validation.py       determinizm, gecikme ve KPI harness'i
src/osc2c/coverage.py         kanıtlı yetenek matrisi
scenarios/                   .osc senaryoları (dev/ mock, carla/ gerçek sunucu)
tests/                       unit + golden + e2e + doğrulama
tools/                       ANTLR jar, bench, coverage, CARLA baseline
docs/                        aşamalar, doğrulama raporu, ölçümler
external/                    CARLA kurulumu (git dışında)
```

## Dokümanlar

- [PROJECT_PLAN.md](PROJECT_PLAN.md) — kapsam, 14 haftalık takvim, riskler
- [ENVIRONMENT.md](ENVIRONMENT.md) — kurulu araçlar ve yollar
- [docs/STAGES.md](docs/STAGES.md) — öğrenme yolu ve aşamalar
- [docs/VALIDATION.md](docs/VALIDATION.md) — Aşama 5 doğrulama ve ölçüm raporu
- [docs/SCOPE_AUDIT.md](docs/SCOPE_AUDIT.md) — plan/gerçek kapsam karşılaştırması ve ertelemeler
- [docs/GRAMMAR_GAPS.md](docs/GRAMMAR_GAPS.md) — dil yapısı bazında destek/eksik tabloları
- [docs/GRAMMAR_DIFF_2.2.md](docs/GRAMMAR_DIFF_2.2.md) — ASAM 2.2.0 EBNF ↔ proje grammar karşılaştırması
- [docs/measurements/](docs/measurements/) — ham JSON/Markdown ölçümler

## Lisans

Kendi kodun için lisans henüz kesinleşmedi (MIT veya Apache-2.0; AVL/danışman görüşü bekleniyor).
Grammar ve üretilen parser MPL-2.0 altındadır; bkz. [NOTICE](NOTICE).
