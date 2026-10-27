# QODER.md

## Proje

Proje adı: **OSC2C** — OpenSCENARIO 2.1 → CARLA Derleyicisi (depo: https://github.com/cankecilioglu/osc2c).
OpenSCENARIO 2.1 DSL'ini CARLA'da çalışan py_trees davranış ağaçlarına çeviren derleyici.
Makale: *Compiling OpenSCENARIO 2.1 for Scenario-Based Testing in CARLA* (arXiv:2604.16452).
Bu bir makale reprodüksiyonudur; resmî ASAM/CARLA ürünü değildir.

Durum: Aşama 0 (ortam), Aşama 1 (lexer/parser/tipli AST), Aşama 2 (sembol tablosu, tipler, birimler), Aşama 3 (runtime + davranış ağaçları), Aşama 4 (CARLA adaptörü + cut-in) ve Aşama 5 (doğrulama + ölçüm) tamam. Sıradaki: tez (Aşama 6).

## Komutlar

```bash
# proje kökünde
.venv/Scripts/activate

# hızlı testler (CARLA gerekmez)
pytest -q

# yalnızca CARLA gerektiren testler
pytest -m carla -q

# grammar'ı yeniden üret
python scripts/generate_parser.py

# tipli AST'yi JSON olarak dök
osc2c ast scenarios/dev/smoke4.osc
osc2c ast scenarios/dev/smoke4.osc --spans

# semantik denetim (sembol tablosu, tip, birim)
osc2c check scenarios/dev/smoke4.osc
osc2c check scenarios/dev/smoke4.osc --strict
osc2c check scenarios/dev/smoke4.osc --dump-symbols
osc2c check scenarios/dev/smoke4.osc --stdlib path/to/types.osc

# davranış ağacı ve mock çalıştırma
osc2c bt scenarios/dev/stage3_sync.osc
osc2c run scenarios/dev/stage3_sync.osc --ticks 200 --dt 0.1 --trace

# gerçek CARLA sunucusunda cut-in (sunucu 2000 portunda açık olmalı)
osc2c run scenarios/carla/cut_in.osc --carla --map Town10HD_Opt --spawn-index 20 --ticks 300 --trace

# doğrulama/ölçüm (CARLA'sız)
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 \
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md
python tools/coverage.py --json docs/measurements/coverage.json \
  --markdown docs/measurements/coverage.md

# 20 tekrarlı CARLA cut-in ölçümü (sunucu açık olmalı)
python tools/bench.py --mode carla --carla-repeat 20 \
  --json docs/measurements/carla.json --markdown docs/measurements/carla.md

# derleyicisiz kontrol grubu
python tools/baseline_carla.py --repeat 5 --json docs/measurements/baseline_carla.json

# golden AST'leri bilinçli değişiklikten sonra yenile
# (Git Bash) UPDATE_GOLDEN=1 pytest -q
```

Windows'ta `python` Store alias'ına gidebilir; venv içindeki `.venv\Scripts\python.exe` kullanılmalı.

## Semantik katman

- İki geçiş: **definition** (her şeyi kapsamına kaydet) → **resolution** (tipleri bağla, kalıtımı çöz, gövdeleri denetle).
- Fiziksel tipler 8'lik SI boyut demetiyle temsil edilir; birim uyumu boyut eşitliğiyle kontrol edilir.
- ASAM `types.osc` / `domain.osc` repoda yok. `semantics/stdlib.py` yerleşik bir alt küme sağlar; `--stdlib` ile harici dosya öncelik kazanır.
- Tanılama kodları kararlıdır: `E01xx` tanım, `E02xx` tip/ifade, `E03xx` kalıtım/genişletme, `E04xx` isim/çağrı, `W01xx` uyarı.
- Uyarı politikası: aktör/scenario/action üzerinde tanımsız metot `W0105` (harici alan olabilir), struct üzerinde aynı durum `E0403` (kesin hata).

## Backend ve runtime

- `serial` → `Sequence(memory=True)`, `parallel` → `Parallel(SuccessOnAll)`, `one_of` → `Parallel(SuccessOnOne)`.
- `one_of` için `Selector` kullanılmaz: `Selector` ilk `RUNNING` çocukta durur ve sonraki alternatifleri hiç ticklemez; makaledeki `drive` + `wait` yarışı ancak `SuccessOnOne` ile çalışır.
- `drive`/`walk` süreli davranıştır ve `RUNNING` döner; diğer atomik aksiyonlar komut kabul edilince `SUCCESS` olur.
- Olaylar blackboard'da kalıcıdır (latched); `rise`/`fall` ilk gözlemi yalnızca kaydeder, sonraki değişimde tetiklenir.
- İfadeler SI birimleriyle değerlendirilir; `UnitInfo.to_si` tek dönüşüm noktasıdır.
- `MockAdapter` varsayılan simülatördür; `osc2c bt`/`run` CARLA gerektirmez.
- Desteklenmeyen davranış sessizce yok sayılmaz: derleme uyarısı + `UnsupportedLeaf` (FAILURE).

## CARLA adaptörü

- `ScenarioInitializer` derleme sırasında `at: start` aksiyonlarını (`assign_position`, `change_lane`, `change_speed`, `set_lights`, `assign_celestial_position`) bir kez uygular; ağaçta bu düğümler `Success` olur. `drive`/`walk` başlangıçta çalıştırılmaz.
- Adaptör synchronous mode + sabit delta kullanır; spawn/teleport yalnızca `world.tick()` ile işlendiği için adaptör bu noktalarda tick atar.
- Spawn noktaları `_left_lane_horizon` ile (0/20/40/60 m sol şerit görüşü) sıralanır; `--spawn-index` sıralamadaki başlangıcı kaydırır, dolu noktalar atlanır.
- `ahead_of` `waypoint.s` farkıyla değil, ileri vektör üzerine izdüşümle hesaplanır; `s` bazı yollarda seyahat yönünde azalır.
- `change_lane` hedef şerit kimliği + şerit merkezine 0.7 m yaklaşma + en az 0.4 s ile tamamlanır; 6 s'de zaman aşımı. Yol kimliği kavşaklarda değiştiği için tek başına kullanılmaz.
- Direksiyon her tick `waypoint.next()` hedefine göre saf takip (pure pursuit) ile üretilir; şerit değişiminde kısa bakış mesafesi kullanılır. `VehicleControl` her tick sıfırdan kurulur (`reverse=False`), çünkü `get_control()` bazı alanları başlatılmamış döndürür.
- `close()` aktörleri yok edip tick atar, sonra settings/weather'ı geri yükler; idempotenttir.

## Doğrulama ve ölçüm

- `src/osc2c/validation.py` derleyicinin **kamusal giriş noktalarını** kullanır (CLI ile aynı yol); ölçüm için özel kısayol yoktur.
- Trace hash: her tick'te aktörlerin `s`, şerit, hız, ışık ve `x/y/z` değerleri 6 ondalığa yuvarlanıp sıralı JSON'a yazılır, SHA-256 alınır. 20 tekrarın hash'i karşılaştırılır.
- KPI'lar: minimum Öklid mesafe, minimum TTC, çarpışma sayısı, cut-in anındaki yanal/başlık/`ahead_of` değerleri ve geometri eşiği.
- `src/osc2c/coverage.py` 43 yetenek satırını durum + kanıt yolu + gerekçeyle tutar; `validate_matrix()` geçersiz durumu, var olmayan kanıt yolunu/test fonksiyonunu ve yinelenen satırı reddeder.
- `tools/bench.py`, `tools/coverage.py` ve `tools/baseline_carla.py` paket dışındadır; baseline doğrudan `carla` import eder, bu istisna yalnızca `src/osc2c/adapters/carla.py` kuralını korur.
- Sonuçlar (2026-10-26): mock 5/5 SUCCESS ve her senaryoda tek hash; CARLA 20/20 SUCCESS, 20/20 geometri, tek hash; tick medyanı 5.45 ms, baseline tam döngüsü 5.38 ms; kapsam 24 desteklenen / 10 kısmi / 9 desteklenmeyen.
- İlk CARLA koşusu ısınma nedeniyle ~4 s derleme gösterir; rapor medyan/steady-state kullanır. Ayrıntı: `docs/VALIDATION.md`.

## Mimari değişmezler

- **Frontend semantik bilmez.** Parser yalnızca sözdizimi üretir; tip/kapsam çözümlemesi orta katmanda yapılır.
- **Orta katman AST'yi anotasyonlar.** Sembol tablosu, tipler ve birimler burada çözülür; CARLA importu yoktur.
- **CARLA importu yalnızca `src/osc2c/adapters/carla.py` içinde.** Diğer modüller `SimAdapter` arayüzünü kullanır.
- **Mock adapter testlerin bel kemiğidir.** CARLA'sız çalışan testler varsayılan; CARLA testleri `@pytest.mark.carla`.
- **Üretilen parser elle düzenlenmez.** `src/osc2c/frontend/generated/` ANTLR çıktısıdır; değişiklik `grammar/openscenario2.g4` içinde yapılır.
- **Her yeni OSC2 yapısı için:** pozitif parse testi + negatif semantik testi + (uygunsa) golden BT testi.

## Grammar ve lisans

- `grammar/openscenario2.g4`, PMSF py-osc2 grammar'ından (MPL-2.0) türetilmiştir.
- Eklenenler: top-level `use`, boşluklu fiziksel literal (`35 kph`), bileşik birim ifadesi (`m/s`, `m/s^2`), `enum_member_value` düzeltmesi.
- Grammar ve üretilen parser MPL-2.0 altındadır; ayrıntı `NOTICE` dosyasında.
- ASAM 2.2.0 paketi `external/asam/` altında yerel tutulur ve `.gitignore` kapsamındadır; dağıtım izni olsa da repoya alınmadı. Testler dosyalar yoksa `skipif` ile atlanır.

## Test ve bitmişlik

- Testler `pytest -q` ile yeşil olmalı (169 mock/doğrulama testi); CARLA testleri ayrı marker'da (3 test, `pytest -m carla -q`; toplam 172).
- CARLA testleri sunucu yoksa `skip` olur; varsayılan paket sunucu gerektirmez.
- Golden AST/BT dosyaları gerçek çıktıyı temsil eder; değişiklik bilinçliyse güncellenir.
- Yeni özellik = kod + test + dokümantasyon. Testi olmayan özellik bitmiş sayılmaz.

## Öğrenme

- `docs/STAGES.md`: aşama aşama kavramlar, çıktılar ve kendini test etme soruları.
- `docs/VALIDATION.md`: Aşama 5 ölçüm sonuçları, yöntem, sınırlılıklar.
- `docs/SCOPE_AUDIT.md`: plan/gerçek kapsam karşılaştırması, ertelenen kalemler ve denetim düzeltmeleri.
- `docs/GRAMMAR_GAPS.md`: dil yapısı bazında destek/eksik tabloları ve öncelikli kalan işler.
- `docs/GRAMMAR_DIFF_2.2.md`: ASAM 2.2.0 EBNF ↔ proje grammar karşılaştırması, kapatılan boşluklar ve kalan semantik sınırlar.
- `PROJECT_PLAN.md`: takvim, kapsam ve riskler.
- `ENVIRONMENT.md`: kurulu araçlar, yollar ve kurulum komutları.
