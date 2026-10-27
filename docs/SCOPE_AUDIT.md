# Kapsam Denetimi — 26 Ekim 2026

Bu belge, `PROJECT_PLAN.md` içindeki Must/Should kalemlerini aşama 5 sonunda
gerçekten teslim edilen kod, test ve ölçümlerle karşılaştırır. Amaç eksikleri
gizlemek değil; her kalemin durumunu, kanıtını ve bilinçli erteleme gerekçesini
izlenebilir kılmaktır.

## 1. Denetim yöntemi

- `PROJECT_PLAN.md`, `ENVIRONMENT.md`, `README.md`, `QODER.md`, `docs/STAGES.md`
  ve `docs/VALIDATION.md` baştan sona okundu.
- `src/osc2c/` altındaki frontend, semantics, backend, runtime, adapters,
  validation ve coverage modülleri; `tools/` ve `tests/` envanteri çıkarıldı.
- `pytest -q -m "not carla"`, `pytest -q -m carla`, `pip check` ve
  `python -m compileall` çalıştırıldı.
- Ertelenen yapıların kullanıcıya nasıl göründüğü küçük kaynaklarla denendi
  (aşağıdaki tabloda tanılama kodları gerçek çıktıdan alınmıştır).

Sonuç: aşama 5 teslimi çalışır durumda; aşağıdaki "ertelendi" kalemleri dışında
planın Must kapsamı karşılanmıştır. Ertelenen kalemler sessizce yutulmaz,
tanılama veya derleme uyarısı üretir.

## 2. Must kalemleri

| Alan | Kalem | Durum | Kanıt / not |
|---|---|---|---|
| Frontend | `import`, `use`, `scenario` | Tamam | Parser + CLI; yerel ASAM dosyaları `--stdlib` ile bağlanır |
| Frontend | `vehicle`, `environment` aktörleri | Tamam | Mock ve CARLA adaptörleri |
| Frontend | `stationary_object`, `map` | Ertelendi | Kullanılırsa `E0201 unknown type`; ayrı spawn/yol semantiği gerektirir |
| Frontend | `keep(...)` | Kısmi | `keep(it.<alan> == değer)` uygulanır; diğer boolean keep'ler doğrulanır, uygulanmaz ve derleme uyarısı verir |
| Frontend | `var`, fiziksel birimler | Tamam | `kph`, `mph`, `m/s`, `m`, `s`, `deg`, `rad`; SI'ya çevrilir |
| Frontend | `with` modifier'ları | Kısmi | `speed`, `lane`, `position` çalışır; `rate_profile` → `W0104` |
| Frontend | `serial`, `parallel`, `one_of` | Tamam | Golden BT testleri |
| Frontend | `wait`, `rise`, `fall`, `elapsed`, `emit`, `@event` | Tamam | Blackboard ve kenar algılama testleri |
| Frontend | Kaynak konumlu tanılama | Tamam | `E01xx`–`E04xx`, `W010x` kodları |
| Semantics | İç içe kapsamlar, iki geçiş | Tamam | `semantics/builder.py`; sembol tablosu testleri |
| Semantics | Kalıtım | Tamam | `vehicle → traffic_participant` |
| Semantics | Fiziksel tip/birim sistemi | Tamam | `PhysicalTypeInfo`, `UnitInfo` |
| Semantics | `stdtypes` / `domain.osc` fallback | Tamam | Minimal yerleşik stdlib + `--stdlib` |
| Semantics | Pozitif/negatif testler | Tamam | `tests/test_semantics.py` |
| Backend | İfade değerlendirici | Tamam | `runtime/context.py`; SI birimleriyle |
| Backend | Aktör arama | Tamam | Adaptör sözlükleri O(1) |
| Backend | `ahead_of` / Euclidean mesafe | Kısmi | `position.ahead_of()`, `position.euclidean()`; ASAM `object_distance(direction: euclidean)` adı yok → `E0402` |
| Backend | `rise` / `fall` / olay blackboard'u | Tamam | `runtime/blackboard.py`, `WaitLeaf` |
| Backend | py_trees `Sequence`, `Parallel`, `SuccessOnOne` | Tamam | `backend/compiler.py` |
| Backend | Otomatik timeout sarmalayıcıları | Ertelendi | Senaryoda `wait elapsed(...)` elle kullanılabilir |
| Backend | `drive` / şerit takibi | Kısmi | Şerit merkezini takip eder; açık waypoint/path API'si yok |
| Backend | `change_speed` | Kısmi | Oransal gaz/fren; PID yok |
| Backend | `change_lane` | Tamam | OpenDRIVE şerit offsetleri; CARLA'da tamamlanma ölçümü |
| Backend | `assign_position` | Tamam | Lane, göreli ve mutlak modlar |
| Backend | `set_lights` | Tamam | Bilinmeyen mod artık `ValueError` üretir |
| Backend | `assign_celestial_position` | Tamam | Azimuth/elevation adaptöre uygulanır |
| Backend | `ScenarioInitializer` üç yerleştirme modu | Tamam | `at: start` aksiyonları derleme anında |
| Backend | `role_name` eşlemesi | Tamam | CARLA blueprint attribute |
| CARLA | Synchronous mode, sabit adım | Tamam | `fixed_delta_seconds` |
| CARLA | Araç spawn/teleport | Tamam | `CarlaAdapter`; yaya/statik nesne ertelendi |
| CARLA | Cut-in senaryosu | Tamam | 20/20 koşu, geometri ve KPI testi |
| CARLA | Demo videosu | Teslim aşaması | Kod kapsamı dışında |
| Doğrulama | 5 senaryo mock e2e | Tamam | `tests/test_validation.py` |
| Doğrulama | 1 senaryo CARLA e2e | Tamam | `tests/test_carla.py`, `@pytest.mark.carla` |
| Doğrulama | 20 tekrarda determinizm | Tamam | SHA-256 trace hash, tek hash |
| Doğrulama | Derleme/tick ölçümü | Tamam | `src/osc2c/validation.py`, `tools/bench.py` |
| Doğrulama | Table 2 kapsam matrisi | Tamam | 43 satır, kanıt doğrulamalı |

## 3. Should kalemleri

| Kalem | Durum | Not |
|---|---|---|
| Hava durumu, trafik ışıkları | Yapılmadı | Adaptör hava durumunu saklar/geri yükler; OSC davranışı yok |
| `follow_path`, `follow_trajectory` | Yapılmadı | Kapsam matrisinde `unsupported` |
| Time gap / space gap / headway | Kısmi | Mekânsal `ahead_of` ve projeksiyon var; zaman açığı yok |
| Orientation modifier'ları | Kısmi | Yalnızca yaw (`h`); pitch/roll yok |
| Elle yazılmış CARLA baseline | Tamam | `tools/baseline_carla.py`, sonuçlar `docs/measurements/` |
| ScenarioRunner karşılaştırması | Ertelendi | Tez dönemi opsiyonu |

## 4. Teslim (D8) kalemleri

| Kalem | Durum | Not |
|---|---|---|
| README, kurulum, doğrulama raporu | Tamam | Bu depo |
| Testler ve tekrarlanabilir ölçümler | Tamam | 169 CARLA'sız + 3 CARLA testi |
| `LICENSE` | Bekliyor | AVL/danışman lisans tercihi netleşince eklenecek |
| CI (GitHub Actions) | Bekliyor | Teslim aşamasında |
| Demo videosu | Bekliyor | Teslim aşamasında |
| Public `v0.1` etiketi | Bekliyor | Onay sonrası |

## 5. Ertelenen kalemlerin kullanıcıya görünümü

Ertelenen bir yapı sessizce yok sayılmaz:

| Kullanım | Sonuç |
|---|---|
| `box : stationary_object` | `E0201 unknown type 'stationary_object'` |
| `m : map` | `E0201 unknown type 'map'` |
| `speed(...)` yanında `rate_profile()` | `W0104 unknown modifier 'rate_profile'` |
| `object_distance(...)` | `E0402 unknown method or behavior` |
| Desteklenmeyen davranış (örn. `fly()`) | Derleme uyarısı + `FAILED` yaprak, çalışmada `unsupported` listesi |
| Desteklenmeyen `keep` biçimi | Derleme uyarısı; kısıt doğrulanır ama uygulanmaz |

Not: Bu tablo yerleşik alt küme modunu anlatır. `--stdlib` ile gerçek ASAM
2.2.0 kütüphanesi yüklendiğinde `stationary_object` ve `map` çözülür;
`rate_profile`/`object_distance` hataları ise çağrı biçimi ve bağlamından
kaynaklanır (bkz. [`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) §4).

## 6. Bu denetimde düzeltilenler

1. **Kapsam matrisi dürüstleştirildi.** Birleşik "Move / drive / walk"
   satırı `Drive` (supported) ve `Walk` (partial) olarak ayrıldı; yaya
   `walk` davranışı mock adaptörde test edildi
   (`test_pedestrian_walk_moves_actor`). CARLA'da yaya spawn edilmediği için
   satır artık `partial`.
2. **Matris doğrulaması güçlendirildi.** `validate_matrix()` yinelenen
   satırları ve var olmayan test fonksiyonlarını da reddeder; kanıt artık
   yalnızca dosya yoluna değil, gerçek test sembolüne bağlı.
3. **CLI hata yolu düzeltildi.** `osc2c ast olmayan.osc` artık iz bırakmadan
   `1` döner ve temiz hata mesajı yazar.
4. **Kullanılmayan `numpy` bağımlılığı kaldırıldı**; `requires-python` 3.12'ye
   çekildi.
5. **`.gitignore` tamamlandı:** `*.egg-info/`, `stdlib/`, `.coverage.*`,
   `coverage.xml`.
6. **CARLA adaptörü tutarlılaştırıldı.** Eski "stage 4" mesajı kaldırıldı;
   bilinmeyen ışık modu artık sessizce `NONE` olmuyor, `ValueError` üretiyor.
7. **Desteklenmeyen `keep` biçimleri raporlanıyor.** Doğrulanan ama
   uygulanmayan kısıtlar derleme uyarısına dönüşüyor.
8. **Dokümantasyon senkronize edildi.** README, QODER, STAGES, VALIDATION ve
   PROJECT_PLAN içindeki 42/23/10/9, %55/%67 ve 103 test değerleri güncel
   sonuçlarla değiştirildi; plan içindeki Python 3.11, `py-osc2`, `numpy`,
   `Town06`, `osc2parser` ve `scripts/fetch_stdlib.py` referansları düzeltildi.

## 7. Doğrulama

```bash
./.venv/Scripts/python.exe -m pytest -q -m "not carla"
./.venv/Scripts/python.exe -m pytest -q -m carla
./.venv/Scripts/python.exe tools/coverage.py --json docs/measurements/coverage.json --markdown docs/measurements/coverage.md
./.venv/Scripts/python.exe -m pip check
```

Beklenen:

- 169 CARLA'sız test + 3 CARLA testi yeşil.
- Kapsam matrisi: 43 satır, 24 supported, 10 partial, 9 unsupported
  (katı %56, ağırlıklı %67), `validate_matrix()` boş liste.
- `pip check`: kırık bağımlılık yok.

CARLA testleri yalnızca sunucu açıkken çalışır; varsayılan paket sunucu
gerektirmez.

## 8. Kalan riskler ve sonraki adımlar

1. **Grammar fark analizi tamamlandı** (plan görevi W2); ayrıntı
   [`docs/GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) ve
   [`docs/GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) içinde. ASAM 2.2.0
   grammar'ı ve kütüphanesiyle mekanik diff yapıldı; üç sözdizimi boşluğu
   kapatıldı. Kalan sınırlar: `*` içeren bileşik birimler (`kg*m/s^2`) ve
   noktalı davranış adlarının hedef tipe bağlanması (`hero.drive()` →
   `W0105`).
2. **Eylem gövdeleri derlendi.** `call action(...)` artık parametre/kapsam
   yönetimiyle çalışıyor; konumsal/adlandırılmış argümanlar, varsayılanlar ve
   aktör parametreleri bağlanıyor. Kalan sınırlar: action kalıtımında gövde
   birleştirme, aktör tipli yerel değişkenlerin spawn edilmesi ve
   `call scenario(...)`.
3. **Yaya ve statik nesne desteği** CARLA'da yok. Mock'ta yaya `walk` var;
   CARLA tarafı tez dönemine bırakıldı.
4. **PID hız kontrolü ve zaman aşımı sarmalayıcıları** yok; mevcut oransal
   kontrol ve elle `wait elapsed(...)` yeterli.
5. **Lisans/CI/demo videosu** teslim aşamasında tamamlanacak; kod kapsamı
   dışında.
6. **Ölçümler tek makine ve tek harita** (`Town10HD_Opt`); farklı donanım veya
   haritalarda determinizm iddiası kurulmadı.
