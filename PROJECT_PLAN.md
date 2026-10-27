# Bitirme Projesi Planı — OSC2C: OpenSCENARIO 2.1 → CARLA Derleyicisi

**Sürüm:** 1.0
**Tarih:** 26 Ekim 2026
**Hedef:** 31 Ocak 2027'ye kadar makalenin çalışan, test edilmiş, açık kaynak uygulaması; Şubat 2027'den itibaren tez dönemi.

---

## 0. Yönetici özeti

Makale, ASAM OpenSCENARIO 2.1 DSL'ini CARLA simülatöründe çalıştırılabilir py_trees davranış ağaçlarına çeviren üç aşamalı bir derleyici tarif ediyor:

1. **Frontend:** ANTLR4 ile lexing/parsing → tipli AST
2. **Middle-end:** sembol tablosu, kapsam çözümleme, tip/birim doğrulama
3. **Backend/runtime:** py_trees üretimi, MethodRegistry, ExecutionContext, CARLA adaptörü

Makalenin kodu veya grammar'ı yayınlanmamıştır. Bu nedenle proje, tarif edilen mimarinin **sıfırdan, açık kaynak ve tekrarlanabilir** biçimde yeniden kurulmasıdır. Ocak sonuna kadar hedef, makalenin Table 2 yetenek matrisinin seçilmiş bir alt kümesini ve Listing 1–3'teki cut-in senaryosunu uçtan uca çalıştırmaktır.

**Ana strateji:** CARLA'yı en sona bırak; derleyicinin büyük kısmını `MockAdapter` ile simülatörsüz geliştir ve test et. Böylece kurulum/performans riski projeyi kilitlemez.

---

## 1. "Açık kaynak yeniden kurma" ne demek?

Makale yalnızca mimariyi anlatıyor; kod vermiyor. "Açık kaynak yeniden kurma" şu anlama gelir:

- Tarif edilen sistemi **kendi kodunla** yazmak.
- Kodu, README, lisans, testler ve kurulum adımlarıyla birlikte **başkalarının indirip çalıştırabileceği** hale getirmek.
- Mevcut açık kaynak parçaları kullanmak (py-osc2 grammar, py_trees, CARLA) ve kaynak göstermek.
- Kendi kodun için bir lisans seçmek (MIT veya Apache-2.0).
- "Kopyalamak" değil; **şeffaf, tekrarlanabilir ve ölçülebilir** bir uygulama ortaya koymak.

Tez açısından değeri: literatürde kod bulunmayan bir yöntemin çalışan, doğrulanmış ve yeniden üretilebilir uygulamasını sunmak. AVL ve danışman onayına kadar repo **private** kalabilir; onay sonrası public yapılır.

---

## 2. Kapsam

### 2.1 Ocak sonuna kadar — Must (zorunlu)

> **Uygulama durumu (26 Ekim 2026):** Bu liste Ocak hedefidir; aşama 5 sonunda
> teslim edilen kapsam ve bilinçli ertelemeler
> [`docs/SCOPE_AUDIT.md`](docs/SCOPE_AUDIT.md) içinde kalem kalem izlenir.
> Grammar 2.1 fark analizi [`docs/GRAMMAR_GAPS.md`](docs/GRAMMAR_GAPS.md)
> içinde tamamlandı. Ertelemeler sessizce yok sayılmaz: kullanıldığında
> semantik hata veya `unsupported` uyarısı üretir.

**Dil / frontend**
- `import`, `use`, `scenario`
- Aktör tanımları: `vehicle`, `environment` (`stationary_object` ve `map`
  ertelendi — bkz. kapsam denetimi)
- `keep(...)` kısıtları (aktör alanı eşitliği)
- `var` ve fiziksel birimler: `kph`, `mph`, `m/s`, `m`, `s`, `deg`, `rad`
- `with` blokları ve modifier'lar: `at`, `side`, `side_of`, `behind`,
  `distance`, `speed`, `lane`, `position` (`rate_profile` ertelendi)
- Kompozisyon: `do serial`, `do parallel`, `serial`, `parallel`, `one_of`
- Olaylar: `wait`, `rise`, `fall`, `elapsed`, `emit`, `@event`
- Kaynak konumlu hata mesajları

**Semantik**
- Global ve iç içe kapsamlar (namespace, struct, actor, method)
- İki geçişli çözümleme: definition pass + resolution pass
- Kalıtım: `vehicle` → `traffic_participant`
- Fiziksel tip sistemi ve birim dönüşümü
- `stdtypes` / `domain.osc` fallback çözümlemesi
- Pozitif ve negatif testler (tanımsız sembol, tip hatası, birim hatası, geçersiz modifier)

**Runtime / backend**
- İfade değerlendirici ve birim dönüşümleri
- Aktör arama önbelleği (O(1))
- `ahead_of` (topolojik/OpenDRIVE) ve `object_distance(direction: euclidean)` ayrımı
- Olay blackboard'u, `rise`/`fall` kenar algılama
- py_trees: `Sequence`, `Parallel`, `Selector` (`SuccessOnOne`); otomatik
  timeout sarmalayıcıları ertelendi (elle `wait elapsed(...)` kullanılabilir)
- MethodRegistry ve atomik davranışlar:
  - `drive` / waypoint takibi
  - `change_speed` (oransal hız kontrolü; PID ertelendi)
  - `change_lane` (OpenDRIVE şerit offsetleri)
  - `assign_position` (lane / relative / absolute)
  - `set_lights`
  - `assign_celestial_position`
- `ScenarioInitializer`: 3 yerleştirme modu (default map, relative topological, absolute Cartesian)
- `role_name` eşlemesi

**CARLA**
- Synchronous mode, sabit `fixed_delta_seconds`
- Aktör spawn/teleport
- Listing 1–3 cut-in senaryosunun çalışması
- Demo videosu (teslim aşamasında)

**Doğrulama**
- 5 senaryo mock backend'de uçtan uca
- 1 senaryo (cut-in) CARLA'da
- 20 tekrarda determinizm (trace hash)
- Derleme süresi ve tick başına gecikme ölçümü
- Table 2 kapsam matrisi (desteklenen / kısmi / desteklenmeyen + test bağlantısı)

#### 2.1.1 Frontend gerçekliği (26 Ekim doğrulaması)

Kurulan py-osc2 0.1.0 grammar'ı OSC 2.0 seviyesinde. Doğrulanan durum:

- **Çalışıyor:** `scenario`, `vehicle`, `keep`, `var`, `at:`, `side_of`, `one_of`, `serial/parallel`, `rise/fall`, `emit`, `wait @event`, `with` blokları.
- **Eksik:** Dosya başındaki `use std.stdtypes` (grammar'da yalnızca namespace içinde var).
- **Fark:** `35 kph` gibi boşluklu fiziksel literal tek token olarak eşleşmiyor; `35kph` çalışıyor. Kaynak kodda hangi yazımın kullanılacağı netleştirilecek.
- **Spike sonucu (26 Ekim):** Grammar MPL-2.0 temel alınarak genişletildi; top-level `use` ve boşluklu fiziksel literal kuralları eklendi, ANTLR 4.13.2 ile yeniden üretildi. Paper tarzı iç içe `serial/parallel`, `emit`, `wait elapsed` ve birimli ifadeler 0 hatayla parse ediliyor. py-osc2 bağımlılığı kaldırıldı; grammar projeye vendored edildi (MPL-2.0 bildirimiyle). Kalan 2.1 farkları W2'de tarandı; sonuç [`docs/GRAMMAR_GAPS.md`](docs/GRAMMAR_GAPS.md) içinde. Bileşik birimler (`m/s`, `km/h`, `m/s^2`) grammar, anlamsal katman ve runtime'a eklendi.

### 2.2 Should (zaman kalırsa)

- Hava durumu (yağmur, sis), trafik ışıkları
- `follow_path`, `follow_trajectory`
- Time gap / space gap / headway
- Orientation modifier'ları
- Elle yazılmış CARLA script'i ile karşılaştırma
- ScenarioRunner karşılaştırması (opsiyonel)

### 2.3 Ocak sonuna kadar kapsam dışı

- Tam OSC 2.1 ontolojisi
- Yaya niyeti, kavşak geçiş hakkı
- Olasılıksal hava durumu
- ROS 2 entegrasyonu
- LLM ile senaryo üretimi
- C++ optimizasyonu

Bu maddeler "desteklenmiyor" tanılamasıyla açıkça raporlanır; sessizce yok sayılmaz.

### 2.4 Tez dönemi (Şubat–Haziran 2027)

- Kapsamı genişletme: yaya, kavşak, KPI hesaplama
- Tam değerlendirme ve tez yazımı
- Opsiyonel uzantı: LLM → OSC 2.1 → CARLA hattı
- Opsiyonel: bildiri/workshop başvurusu

---

## 3. Mimari

```text
.osc2 kaynak
    │
    ▼
[Frontend]  ANTLR4 parser + ASTTransformer
    │        → tipli AST, kaynak konumları
    ▼
[Middle-end]  SymbolTable + Resolver + TypeSystem
    │        → anotasyonlu AST + GlobalScope
    ▼
[Backend]  BehaviorTreeBuilder + MethodRegistry
    │        → py_trees davranış ağacı
    ▼
[Runtime]  ExecutionContext + event blackboard
    │
    ├── MockAdapter   (test/CI, simülatörsüz)
    └── CarlaAdapter  (demo/ölçüm)
```

Repo iskeleti:

```text
osc2-carla/
├─ QODER.md
├─ README.md
├─ LICENSE
├─ NOTICE
├─ grammar/openscenario2.g4        # py-osc2 (MPL-2.0) referansı
├─ stdlib/                          # types.osc, domain.osc (repoya koyma)
├─ src/osc2c/
│  ├─ frontend/    parser, ast, transformer
│  ├─ semantics/   symbols, types, units, resolver
│  ├─ backend/     bt_builder, registry, initializer
│  ├─ runtime/     context, events, atomic_behaviors
│  └─ adapters/    base.py, carla.py, mock.py
├─ scenarios/
├─ tests/           unit + golden + e2e
└─ tools/           bench.py, coverage.py
```

---

## 4. 14 haftalık takvim (26 Ekim 2026 – 31 Ocak 2027)

| Hafta | Tarih | Odak | Çıktı / kapı |
|---|---|---|---|
| W1 | 26 Eki – 1 Kas | Plan, ortam, repo, parse spike | Python/Java/CARLA kurulu; Listing 1 parse edilip AST dump ediliyor (G0) |
| W2 | 2 – 8 Kas | Grammar gap analizi; top-level `use` ve fiziksel literal kuralları; AST düğümleri | Genişletilmiş grammar; Listing 1–3 parse; gap analizi `docs/GRAMMAR_GAPS.md` |
| W3 | 9 – 15 Kas | ASTTransformer, tanılama, golden testler | 10 parser testi; G1: tüm listing'ler parse |
| W4 | 16 – 22 Kas | Sembol tablosu, kapsamlar, definition pass | Sembol tablosu testleri |
| W5 | 23 – 29 Kas | Resolution pass, kalıtım, tip/birim sistemi, stdtypes | Tip/birim çözümleme çalışıyor |
| W6 | 30 Kas – 6 Ara | İfade değerlendirici, birim dönüşümleri, negatif testler | G2: listing'ler semantik olarak geçerli; 15 negatif test |
| W7 | 7 – 13 Ara | BT builder, olay blackboard'u, kenar algılama, mock iskeleti | BT kompozitleri test edildi |
| W8 | 14 – 20 Ara | Mock atomik davranışlar + Listing 1–3 uçtan uca | G3: mock e2e yeşil; trace assertion'ları |
| W9 | 21 – 27 Ara | Tatil / sınav / buffer / CARLA kurulum denemeleri | CARLA smoke test |
| W10 | 28 Ara – 3 Oca | Yılbaşı / buffer / dokümantasyon | Opsiyonel erken CARLA adaptörü |
| W11 | 4 – 10 Oca | CARLA adaptörü, initializer, 3 yerleştirme modu, role_name | G4a: aktörler doğru konumda |
| W12 | 11 – 17 Oca | CARLA atomik davranışları, cut-in senaryosu, kamera | G4b: cut-in CARLA'da çalışıyor |
| W13 | 18 – 24 Oca | 5 senaryo doğrulama, determinizm, benchmark, baseline | Ölçüm raporu taslağı |
| W14 | 25 – 31 Oca | Dondurma, README/lisans/CI, demo videosu, v0.1 etiketi | G5: teslim paketi + AVL demo |

**Buffer:** W9–W10 iki haftalık tampon. Sınav/tatil nedeniyle kayma olursa "Could" maddeleri ve ScenarioRunner karşılaştırması düşer; cut-in + mock doğrulama korunur.

**Go/No-Go:** W8 sonunda mock e2e çalışmıyorsa kapsam daraltılır: CARLA'da yalnızca cut-in gösterilir, Table 2'nin Should maddeleri tez dönemine bırakılır.

---

## 5. Doğrulama planı

### 5.1 Test katmanları

1. **Parser testleri:** Geçerli/geçersiz `.osc` dosyaları, hata konumu ve mesajı.
2. **Golden AST testleri:** AST JSON snapshot'ları; regresyon yakalama.
3. **Semantik testler:** Tanımsız sembol, tip uyuşmazlığı, birim uyuşmazlığı, geçersiz modifier, kalıtım.
4. **Golden BT testleri:** Üretilen py_trees yapısının JSON dump'ı.
5. **Mock e2e:** 5 senaryo; olay sırası, konum/hız assertion'ları.
6. **CARLA e2e:** Cut-in senaryosu; 20 tekrar; trace hash ile determinizm.
7. **Performans:** Derleme süresi (senaryo başına), tick başına gecikme (ms), bellek.
8. **Kapsam:** Table 2 matrisi; her hücre test bağlantısı veya "desteklenmiyor" gerekçesi.

### 5.2 Senaryo seti

| ID | Senaryo | Amaç |
|---|---|---|
| S1 | `cut_in_evasive.osc` | Makalenin Listing 1–3'ü; çok aktörlü olay senkronizasyonu |
| S2 | `lane_change_speed.osc` | `change_lane` + PID hız profili |
| S3 | `event_handshake.osc` | `emit` / `wait @event`; iki aktör |
| S4 | `placement_modes.osc` | Default / relative / absolute yerleştirme |
| S5 | `environment_lights.osc` | Alacakaranlık, ışık, hava durumu |
| N1 | `semantic_errors/` | Negatif tanılama testleri |

### 5.3 Ölçümler

- **Determinizm:** 20 tekrarda tick bazlı konum/hız trace'lerinin hash'i aynı olmalı (sabit dt, sabit seed, synchronous mode).
- **Performans:** Elle yazılmış CARLA Python script'i ile karşılaştırma; ScenarioRunner karşılaştırması zaman kalırsa.
- **KPI:** Çarpışma sayısı, minimum mesafe, minimum TTC, senaryo tamamlama.
- **Kapsam:** Table 2'nin yüzde kaçı destekleniyor; desteklenmeyenlerin listesi.

---

## 6. Teslim edilebilirler

| ID | Teslim | Tarih |
|---|---|---|
| D1 | Bu plan | 26 Eki 2026 |
| D2 | Ortam + repo iskeleti + `QODER.md` | W1 |
| D3 | Frontend (genişletilmiş 2.1 grammar) + parser testleri | W3 |
| D4 | Semantik çözümleyici + negatif testler | W6 |
| D5 | BT + mock runtime + Listing 1–3 e2e | W8 |
| D6 | CARLA adaptörü + cut-in demosu | W12 |
| D7 | Doğrulama raporu + benchmark | W13 |
| D8 | v0.1 açık kaynak sürüm adayı + demo videosu + tez devir dokümanı | W14 |

---

## 7. Açık kaynak ve lisans planı

- **Kendi kodun:** Apache-2.0 (kurumsal iş birliği ve patent grant için) veya MIT. AVL/danışman tercihi netleşince sabitlenir.
- **py-osc2 grammar:** MPL-2.0. Kopyalanır/değiştirilirse dosya MPL lisansıyla kalır; `NOTICE` dosyasında belirtilir.
- **ASAM `types.osc` / `domain.osc`:** Şu an repoda tutulmaz; kullanıcı
  dosyaları ASAM'dan indirip `osc2c check|bt|run --stdlib <dosya>` ile yerel
  olarak bağlar. Paket başlığı "ASAM allows unrestricted distribution of this
  standard" dediği için yeniden dağıtım seçeneği açıktır; karar verilirse
  `NOTICE` güncellenir ve dosyalar `external/asam/` altında izlenir
  (bkz. [`docs/GRAMMAR_DIFF_2.2.md`](docs/GRAMMAR_DIFF_2.2.md) §8).
- **CARLA:** Kendi lisansına tabi; repo'ya binary koyulmaz.
- **Yayın:** Geliştirme sırasında private repo; AVL ve danışman onayından sonra public + `v0.1` etiketi.
- **Atıf:** Makale, py-osc2, CARLA, py_trees, ASAM OpenSCENARIO 2.1.

---

## 8. Riskler ve azaltma

| Risk | Etki | Azaltma |
|---|---|---|
| CARLA kurulumu/AMD performansı | Yüksek | Mock-first; `-quality-level=Low`, düşük çözünürlük, off-screen; gerekirse Linux/cloud |
| Kapsam patlaması | Yüksek | Must/Should/Could; Table 2 alt kümesi; "desteklenmiyor" tanılaması |
| py-osc2 grammar 2.0 seviyesinde | Düşük (kapandı) | ASAM 2.2.0 `grammar.ebnf` ile mekanik diff yapıldı (165 EBNF / 154 parser kuralı); üç boşluk kapatıldı. Ayrıntı: `docs/GRAMMAR_DIFF_2.2.md` |
| ASAM standart dosyalarına erişim | Düşük | 2.2.0 paketi `external/asam/` altında mevcut ve `--stdlib` ile tanılamasız yükleniyor; erişim olmasa da yerleşik alt küme devrede |
| Birim/olay semantiği hataları | Orta | Golden testler; makale örnekleri; negatif testler |
| Zaman (sınav/tatil) | Orta | W9–W10 buffer; W8 go/no-go |
| Açık kaynak onayı | Düşük/Orta | Private geliştirme; onay sonrası yayın |
| Tez özgünlüğü | Orta | Doğrulama + tekrarlanabilirlik + mock backend + (opsiyonel) LLM uzantısı |

---

## 9. AVL / danışman ile netleştirilecekler

1. Repo public olabilir mi? Lisans tercihi ne?
2. Hangi OSC 2.1 yetenekleri/senaryoları öncelikli?
3. ASAM standart dosyaları ve lisansı sağlanacak mı?
4. Teslim/demo formatı ve kabul kriterleri ne?
5. ScenarioRunner karşılaştırması bekleniyor mu?
6. AVL araçlarıyla (örn. SCENARIUS) entegrasyon bekleniyor mu, yoksa yalnızca CARLA mı?

---

## 10. Ortam kurulumu (gerçekleşen)

1. Python 3.12.15 (uv standalone; sistemdeki 3.15 kullanılmıyor)
2. JDK 17 (ANTLR aracı için)
3. CARLA 0.9.16 Windows paketi (`C:\CARLA_0.9.16`)
4. Git + VS Code/Qoder
5. Proje venv'i: `python -m venv .venv`
6. `pip install -e ".[dev]"` (bağımlılıklar: `antlr4-python3-runtime`, `py-trees`, `pytest`, `pytest-cov`)
7. Doğrulama:
   - `python -c "import carla; print(carla.__version__)"`
   - `osc2c --help`
   - `CarlaUE4.exe` ile `Town10HD_Opt` açılışı
8. CARLA performans ayarları: düşük kalite, 1280×720, sabit `fixed_delta_seconds=0.05`

Ayrıntı ve sürüm doğrulaması: [`ENVIRONMENT.md`](ENVIRONMENT.md).

---

## 11. Başarı tanımı

**Minimum başarı (Ocak sonu):**
- Cut-in senaryosu CARLA'da çalışıyor.
- 5 senaryo mock backend'de geçiyor.
- 20 tekrarda determinizm kanıtlanmış.
- Table 2 kapsam matrisi ve doğrulama raporu hazır.
- Repo, README, lisans ve testlerle teslim edilebilir durumda.

**Hedef başarı:**
- Yukarıdakiler + 2 Should senaryosu + elle yazılmış CARLA baseline karşılaştırması + public v0.1.

**Uzatma (tez dönemi):**
- LLM → OSC 2.1 → CARLA hattı, KPI tabanlı otomatik değerlendirme, bildiri.
