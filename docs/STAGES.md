# Proje Aşamaları ve Öğrenme Yolu

Bu doküman, projeyi yaparken hangi kavramı neden kullandığımızı ve her aşamada neyi öğrenmen gerektiğini özetler. Tez savunmasında "bunu neden böyle yaptın?" sorusuna cevap verebilmek için her aşamanın sonundaki soruları kendine sor.

## Aşama 0 — Ortam ve iskelet (tamamlandı)

**Kavram:** Tekrarlanabilir geliştirme ortamı, sanal ortam (venv), bağımlılık sabitleme, sürüm kontrolü.

**Yapılan:**
- Python 3.12 venv (CARLA 0.9.16 bu sürümle çalışıyor; sistemdeki 3.15 ayrı duruyor).
- JDK 17 + ANTLR 4.13.2.
- Grammar spike'ı: top-level `use`, boşluklu ve bileşik fiziksel literaller (`m/s`, `m/s^2`).
- `pytest` ile ilk parser testleri.

**Çıktı:** `pytest -q` yeşil; proje Desktop'ta.

**Kendini test et:**
- CARLA neden Python 3.15 ile kullanılamıyor?
- Grammar'ı değiştirince neden parser'ı yeniden üretiyoruz?
- `venv` neyi izole eder?

## Aşama 1 — Frontend: lexer, parser, AST (tamamlandı)

**Kavram:** Token, lexer, parser, parse tree, AST, visitor, girinti (indentation) duyarlı dil, kaynak konumu.

**Yapılan:**
- `frontend/ast.py`: ~70 tipli düğüm, her düğümde `Span` (dosya, satır, kolon).
- `frontend/transformer.py`: ANTLR parse tree'sini AST'ye çeviren Visitor.
- `frontend/parser.py`: sözdizimi hatalarını toplayıp `ParseError` olarak fırlatan giriş noktası.
- `osc2c ast <dosya>` CLI'ı; `tests/golden/ast/*.json` snapshot'ları.
- Grammar düzeltmesi: `enum_member_value` artık `integer_literal` kullanıyor (lexer `UINT_LITERAL` hiç üretmiyordu).

**Öğrenilen tuzak:** `primary_exp` içindeki `enum_value_reference` kuralı çıplak `v_hero` gibi adları da eşliyordu. Bu ayrım sözdizimiyle yapılamaz; transformer çıplak adı `Identifier` yapar, enum üyeliğine karar vermeyi semantik aşamaya bırakır.

**Çıktı:** `osc2c ast scenarios/dev/smoke4.osc` JSON AST; Aşama 1 sonunda 16 test yeşil (bugün 169 mock/doğrulama + 3 CARLA).

**Kendini test et:**
- Parse tree ile AST arasındaki fark nedir?
- `use` neden lexer kuralı değil de parser kuralı?
- Girinti duyarlı dilde `INDENT`/`DEDENT` neden gerekli?
- Golden test neden AST'nin *tamamını* karşılaştırır; yalnızca birkaç alanı kontrol etmek neyi kaçırır?

## Aşama 2 — Semantik: sembol tablosu, tipler, birimler (tamamlandı)

**Kavram:** Kapsam (scope), sembol tablosu, iki geçişli çözümleme, tip sistemi, fiziksel birimler, kalıtım.

**Yapılan:**
- `semantics/types.py`: primitifler, 8'lik SI boyut demetiyle fiziksel tipler, birim dönüşümü (`to_si`/`from_si`), liste/aralık, enum, composite (struct/actor/scenario/action/modifier), fonksiyon tipi; atanabilirlik (boyut uyumu, `int`→`float`, kalıtım zinciriyle alt tip).
- `semantics/scope.py`: `Symbol`/`Scope`, `SymbolKind`; ad alanları düz kapsam olarak `a::b` anahtarıyla tutulur.
- `semantics/stdlib.py`: ASAM dosyaları yokken kullanılan yerleşik alt küme — `length`, `speed`, `time`, `angle`, `mass`; `m/km/cm/mm`, `s/ms/min/h`, `rad/deg`, `kph/mph/mps`; `traffic_participant`/`vehicle`/`pedestrian`/`environment`, `position`, `speed`/`lane` modifier'ları.
- `semantics/builder.py`: `ModelBuilder` iki geçiş çalıştırır — **definition** (tipler, birimler, enumlar, composite'ler, modifier'lar, parametreler, üyeler) ve **resolution** (birim katsayıları, kalıtım, genişletmeler, imzalar, ifade tipleri, gövdeler, çağrı argümanları). Her düğüm `id(node)` anahtarıyla anotlanır.
- Yerleşik alt küme modunda, açık tabanı olmayan aktörler `std::traffic_participant`'tan türer; bu sayede `name`/`position` alanları ve yerleşik metotlarla uyumluluk kazanır. Gerçek ASAM kütüphanesi yüklendiğinde tabanlar dosyada açıkça yazılıdır (`vehicle → traffic_participant → movable_object → physical_object → osc_actor`).
- `semantics/diagnostics.py`: kararlı kodlu tanılamalar, `--strict` ile uyarıların hataya yükseltilmesi.
- `osc2c check` CLI'ı: `--strict`, `--stdlib FILE`, `--dump-symbols`, `--include-builtins`; göreli `import` zincirleri özyinelemeli yüklenir.
- Testler: altı geliştirme senaryosu hatasız; birim dönüşümü, kalıtım döngüsü, tip uyuşmazlığı, belirsiz ad, argüman hataları ve sembol tablosu determinizmi için negatif/pozitif testler.

**Öğrenilen tuzaklar:**
- `prefixed_identifier` yalnızca tek `::` destekler; `std::stdtypes::speed` doğrudan yazılamaz. Çözüm: `use stdtypes` + kısa ad, ya da `--stdlib` ile harici tanım. Grammar'ı genişletmek yerine mevcut dil kuralına uyuldu.
- Çıplak enum üyesi (`start`) ile değişken adı sözdiziminde aynı görünür; ayrım resolution pass'te, görünür enum'lar üzerinden yapılır. Birden fazla enum'da aynı ad varsa `E0404` belirsizlik hatası verilir.
- "Tanımsız metot" her composite'te hata değildir: aktör/scenario/action harici alan çağırabilir (`W0105`), struct çağıramaz (`E0403`). Bu politika yanlış pozitifleri engellerken yazım hatalarını da yakalar.

**Çıktı:** Anotasyonlu AST + kararlı kodlu tanılamalar; `osc2c check` tüm geliştirme senaryolarında hatasız (yalnızca bilinçli `W0102`/`W0105` uyarıları); `pytest -q` 52 test yeşil.

**Kendini test et:**
- Neden iki geçiş gerekiyor? Tek geçişte ne kırılır?
  → İleri referanslar (bir aktörün sonradan tanımlanan tipe başvurması) ve karşılıklı kalıtım tek geçişte çözülemez; ayrıca gövdeler ancak tüm imzalar bilinince denetlenebilir.
- `vehicle` → `traffic_participant` kalıtımı nerede çözülür?
  → Resolution pass'te, `_resolve_inheritance`; zincir `is_assignable` içinde yukarı doğru yürünerek kontrol edilir.
- `35 kph` ile `9.72 m/s` aynı şey mi; bunu kim garanti eder?
  → Evet, aynı boyut (length/time). `UnitInfo.to_si` katsayıyı uygular; eşitlik `is_assignable`/`common_type` boyut karşılaştırmasıyla garanti edilir.

## Aşama 3 — Runtime ve davranış ağaçları (tamamlandı)

**Kavram:** Davranış ağacı (BT), composite (sequence/parallel/selector), blackboard, olay, kenar algılama (`rise`/`fall`), süreli aksiyon, tick döngüsü.

**Yapılan:**
- `runtime/context.py`: `ExecutionContext`; senaryo parametrelerini aktöre bağlar, `keep(it.name == ...)` kısıtlarını uygular, değişkenleri SI birimleriyle sırayla değerlendirir, kullanıcı metotlarını (`it` üzerinden) çağırır.
- `runtime/blackboard.py`: olaylar ve paylaşılan durum; olaylar kalıcıdır (latched), böylece sonra gelen `wait @event` anında tatmin olur.
- `adapters/__init__.py`: `SimAdapter` protokolü ve `ActorState`; CARLA bağımlılığı hâlâ yalnızca `adapters/carla.py` için ayrılmıştır.
- `adapters/mock.py`: deterministik tek-şeritli yol modeli; `s` boyunca hareket, lane değişimi, ışık ve güneş açısı; `ahead_of` topolojik fark.
- `backend/behaviors.py`: `ActionLeaf`, `WaitLeaf`, `EmitLeaf`, `CallLeaf`, `UnsupportedLeaf`; `elapsed`/`rise`/`fall`/`@event` koşulları.
- `backend/method_registry.py`: `drive`, `walk`, `change_speed`, `assign_position`, `change_lane`, `set_lights`, `assign_celestial_position` eşlemeleri; `position`/`lane` modifier'ları.
- `backend/compiler.py`: `serial` → `Sequence(memory=True)`, `parallel` → `Parallel(SuccessOnAll)`, `one_of` → `Parallel(SuccessOnOne)`; `CompiledScenario.run()` tick döngüsü ve `RunResult`.
- `osc2c bt` (ağaç JSON'u) ve `osc2c run` (mock çalıştırma, `--ticks`, `--dt`, `--trace`); `tests/golden/bt/*.json` snapshot'ları.
- Yeni senaryolar: `stage3_sync.osc` (one_of + rise + emit + elapsed + event), `stage3_parallel.osc`, `stage3_fall.osc`, `stage3_unsupported.osc`.

**Öğrenilen tuzaklar:**
- `one_of` için `Selector` yanlış araçtır: ilk çocuk `RUNNING` ise sonraki alternatifleri hiç ticklemez; makaledeki `drive` + `wait` yarışı kilitlenir. `Parallel(SuccessOnOne)` tüm dalları tickleyip ilk başarıyı kazandırır.
- `rise`/`fall` "şu an doğru mu?" sorusu değildir; ilk gözlem yalnızca önceki durumu kaydeder, tetikleme sonraki değişimde olur. Başlangıçta zaten doğru olan bir koşul `rise` üretmez.
- `drive` süreli bir davranıştır ve `RUNNING` kalır; bir `serial` içinde tek başına senaryoyu bitirmez. `one_of`, `wait` veya timeout ile sonlandırılmalıdır.
- Desteklenmeyen bir davranış sessizce atlanmaz: derleme uyarısı verilir ve ağaçta `FAILURE` üreten bir yaprak oluşturulur.

**Çıktı:** `osc2c run scenarios/dev/stage3_sync.osc` → `SUCCESS`, 22 tick, `SYNCHRONIZED` olayı, `high_beam`; `stage3_parallel` iki dalı 0.5 s'de senkronize eder; `stage3_fall` düşen kenarı yakalar; `pytest -q` 81 test yeşil. Listing 1–3'ün tamamı değil, Listing 2/3'teki kompozisyon ve olay çekirdeği mock'ta çalışıyor; `map`, `stationary_object` ve gerçek CARLA yerleşimi Aşama 4'te.

**Kendini test et:**
- `one_of` neden "ilk başarılı" politikası kullanır?
  → Alternatifler eşzamanlı başlar; hangisi önce biterse senaryo onu seçer. `Selector` sıralıdır ve `RUNNING` bir dalda takılır.
- `rise` ile `fall` arasındaki fark, olay tetiklemede neden önemli?
  → `rise` yanlış→doğru, `fall` doğru→yanlış geçişini bekler; yalnızca anlık değere bakmak, sürekli doğru kalan bir koşulda her tick tetiklenmeye yol açar.
- Blackboard olmadan olay senkronizasyonu nasıl yapılırdı; dezavantajı ne?
  → Paylaşılan bir değişken/global bayrak veya doğrudan nesne referansı gerekirdi; bu, aktörleri birbirine bağlar ve olayın kaçırılması/tekrar tüketilmesi gibi yarış durumları doğurur.
- Süreli bir `drive` neden `serial` içinde tek başına bitmez?
  → Hedef hızı sürdürmeye devam eder ve `RUNNING` döner; bitiş koşulu eklenmedikçe sequence ilerlemez.

## Aşama 4 — CARLA adaptörü (tamamlandı)

**Kavram:** Simülatör API'si, synchronous mode, aktör/spawn, OpenDRIVE, waypoint, saf takip (pure pursuit), başlangıç yerleşimi.

**Yapılan:**
- `SimAdapter` genişletildi: `assign_position(reference, distance, lane_offset)` ve `lane_change_complete(name)`. Mock adapter göreli konumu ve şerit kaydırmayı aynı sözleşmeyle uygular.
- `backend/initializer.py`: `ScenarioInitializer`, `at: start` aksiyonlarını **derleme sırasında bir kez** uygular (`assign_position`, `change_lane`, `change_speed`, `set_lights`, `assign_celestial_position`). Ağaçta bu düğümlerin yerine `Success` yaprağı konur; `drive`/`walk` başlangıçta çalıştırılmaz çünkü süreli davranışlardır.
- `method_registry.py`: `position(distance:, ahead_of:/behind:)`, `lane(side:, side_of:, num_of_lanes:)` ve mutlak `lane` eşlemeleri; `change_lane` artık adaptörün `lane_change_complete` yanıtını bekliyor.
- `adapters/carla.py` (tek `carla` importu):
  - synchronous mode + sabit delta; kapanışta settings/weather geri yükleme ve aktör temizliği.
  - `role_name` eşlemesi; `tesla.model3` / `lincoln.mkz_2017` blueprint'leri.
  - Spawn noktaları aynı yönde 0/20/40/60 m sol şerit görüşüne göre sıralanır; `--spawn-index` bu sıralamada kaydırma yapar, dolu noktalar atlanır.
  - `assign_position`: göreli mesafe, şerit kaydırma ve mutlak şerit; yerleştirme sonrası hızlar sıfırlanır ve fren uygulanır.
  - `drive`: her tick saf takip direksiyonu + hedef hıza göre gaz/fren; `change_lane` sırasında kısa bakış mesafesi.
  - `change_lane`: hedef şerit kimliği + şerit merkezine 0.7 m yaklaşma + en az 0.4 s; 6 s zaman aşımı.
- CLI: `osc2c run ... --carla --host --port --map --spawn-index --fixed-delta`.
- `scenarios/carla/cut_in.osc`: hero 12 m/s, NPC sol şeritte 12 m önde; 2 s sonra sağa şerit değişimi, `CUT_IN` olayı, ardından hero freni ve NPC yavaşlaması.
- `tests/test_carla.py` (`@pytest.mark.carla`): spawn/hareket, cut-in geometrisi, `close()` temizliği ve settings geri yükleme.

**Öğrenilen tuzaklar:**
- CARLA'da `waypoint.s` her yolda seyahat yönünde artmaz; `ahead_of` için ileri vektöre izdüşüm kullanıldı: `dot(p1 - p2, forward(p1))`.
- Synchronous mode'da `try_spawn_actor` ve `set_transform` ancak `world.tick()` ile işlenir; adaptör spawn/teleport sonrası tick atar. `close()` da yok etmeyi tick ile kesinleştirir.
- `get_control()` bazı alanları (özellikle `reverse`/`gear`) başlatılmamış döndürür; araç geri gitmeye başladı. Her tick yeni bir `VehicleControl(reverse=False, manual_gear_shift=False, gear=0)` kuruldu.
- Şerit kimlikleri yol-yereldir ve kavşaklarda değişir; tamamlanma karşılaştırması yalnızca yol kimliğine değil, hedef şerit kimliği + şerit merkezine yaklaşmaya dayanır.
- Şerit değişiminde uzun bakış mesafesi hedef şeridi ıskalattı; manevra sırasında bakış 4–8 m'ye kısaltıldı, normal sürüşte 5–11 m kullanılıyor.
- Tek şeritli/kısa spawn noktaları cut-in'i imkânsız kılar; spawn seçimi sol şerit görüşüne göre sıralanarak dolduruldu.

**Çıktı:** Cut-in CARLA'da `SUCCESS`; başlangıçta NPC bir şerit solda (~3.5 m) ve 12 m önde, `CUT_IN` anında aynı şeritte (|yanal| < 2.2 m), küçük başlık farkı ve hâlâ önde. `pytest -q -m "not carla"` 82 test, `pytest -q -m carla` 3 test yeşil.

**Kendini test et:**
- `ahead_of` (topolojik/izdüşüm) ile Öklid mesafesi neden farklı?
  → Öklid, kuş uçuşu mesafedir; cut-in'de araç yana kaydıkça mesafe büyür. İzdüşüm ise "benim ileri eksenimde ne kadar önümde?" sorusunu yanıtlar ve şerit değişiminde kararlı kalır.
- Synchronous mode determinizme nasıl katkı sağlar?
  → Simülasyon yalnızca `tick()` çağrısında ilerler ve her adım sabit `fixed_delta_seconds` kullanır; böylece aynı girdi dizisi aynı durum dizisini üretir (fizik motorunun çekirdek determinizmi hariç).
- Saf takip (pure pursuit) ile PID arasındaki fark ne?
  → Pure pursuit ileri bir hedef noktaya geometrik yay çizer; PID geçmiş hatayı biriktirir ve kazanç ayarı ister. Bu projede hedef nokta `waypoint.next()` ile üretildiği için pure pursuit daha basit ve kararlıydı.
- `at: start` aksiyonları neden derleme sırasında uygulanıyor, ağaçta neden `Success` görünüyor?
  → Bunlar senaryonun başlangıç koşullarını kurar; her tick yeniden çalıştırılırsa aracı sürekli ışınlar. Bir kez uygulanıp ağaçta başarılı yaprak olarak işaretlenmeleri, `serial` akışının beklendiği gibi ilerlemesini sağlar.

## Aşama 5 — Doğrulama ve ölçüm (tamamlandı)

**Kavram:** Golden test, determinizm, trace hash, benchmark, baseline karşılaştırma, kapsam matrisi, geçerlilik tehdidi.

**Yapılan:**
- Beş senaryoluk doğrulama seti: CARLA cut-in (S1) + `lane_change_speed`, `event_handshake`, `placement_modes`, `environment_lights` (S2–S5). Hepsi `MockAdapter` üzerinde deterministik.
- `src/osc2c/validation.py`: her tick'te aktör durumunu örnekleyip SHA-256 trace hash'i üretir; derleme aşamalarını (parse/analiz/BT) ve tick gecikmesini ölçer; cut-in için minimum mesafe, TTC, çarpışma ve geometri KPI'larını hesaplar.
- `tools/bench.py`: `--mode mock|carla|all`, tekrar sayıları, JSON/Markdown çıktısı.
- `src/osc2c/coverage.py` + `tools/coverage.py`: makale Table 2'yi temel alan 43 satırlık kanıtlı kapsam matrisi (durum + kanıt yolu + gerekçe); `validate_matrix()` tutarlılığı, yinelenen satırları ve geçersiz test kanıtlarını denetler.
- `tools/baseline_carla.py`: derleyiciyi kullanmayan, doğrudan CARLA API'siyle süren kontrol grubu.
- `tests/test_validation.py`: senaryo sonuçları, olaylar, cut-in geometrisi, 20 tekrarlı determinizm, derleme aşamaları ve kapsam matrisi için 14 test.
- Rapor: `docs/VALIDATION.md`; ham veriler `docs/measurements/`.

**Öğrenilen tuzaklar:**
- "Deterministik" tanımlanmadan ölçülemez. Burada kastedilen: aynı senaryo + aynı adaptör ayarları + aynı sabit adımda tick-by-tick aktör durumunun aynı hash'i vermesi. Fizik motorunun farklı makinelerde aynı sonucu vereceği iddia edilmez.
- Hash'e her tick'in tüm aktör durumu girmeli; yalnızca son durumu hash'lemek, yolda ayrışan ama aynı yerde biten iki koşuyu "aynı" sanar.
- CARLA'da ilk koşu ısınma içerir: BT derleme ilk seferde ~4 s, sonra ~16 ms. Ortalama tek başına yanıltıcıdır; medyan + steady-state raporlanmalı.
- Derleme süresi senaryo boyutundan çok parser'ın belirsizlik çözümüne bağlı (2.6–75.2 ms). Tek bir "derleme süresi" değeri vermek yanlış olur.
- Baseline'ı ham engine tick'i ile değil, **tam döngüsüyle** (tick + kontrol hesabı) karşılaştırmak gerekir; aksi hâlde elma-armut kıyaslanır. Baseline ayrıca algoritmik eşdeğer değil, yalnızca maliyet kontrolüdür.
- Table 2 işaretleri PDF'ten çıkarılamadı; işaretleri tahmin etmek yerine her satırı çalışan kanıta bağlayan kendi matrisimiz kuruldu.

**Çıktı:**
- Mock: 5/5 SUCCESS, her senaryoda 20 tekrarda tek hash; derleme medyanı 2.63–75.19 ms (parser baskın), tick p95 ≤ 0.03 ms.
- CARLA: 20/20 SUCCESS, 20/20 geometri, tek hash (`afaf910c…`); `CUT_IN` 3.25 s, |yanal| 1.298 m, minimum mesafe 11.938 m, TTC 24.49 s, 0 çarpışma; tick medyanı 5.45 ms.
- Baseline: 5/5 SUCCESS; tam döngü 5.38 ms — derleyici tick'iyle ~%1.4 fark. Baseline cut-in'i 4.25 s'de tamamlıyor (farklı hız profili/tetikleyici).
- Kapsam: 43 satır → 24 desteklenen, 10 kısmi, 9 desteklenmeyen (katı %56, ağırlıklı %67).
- `pytest -q -m "not carla"` 169 test, `pytest -q -m carla` 3 test yeşil.

**Kendini test et:**
- "Deterministik" derken tam olarak neyi kastediyoruz?
  → Aynı girdi ve aynı simülasyon ayarlarıyla tick dizisinin aynı trace hash'ini üretmesini. Kapsam: aynı makine, aynı CARLA sürümü, aynı harita/spawn, synchronous mode + sabit delta. Fizik motorunun mutlak determinizmi ayrı bir iddiadır ve burada kanıtlanmadı.
- Hangi metrik derleyicinin başarısını, hangisi runtime'ın başarısını ölçer?
  → Derleme süresi ve kapsam matrisi derleyicinin (dil kapsamı + ön yüz maliyeti) başarısını; tick gecikmesi, KPI'lar ve olay zamanlaması runtime/adaptörün başarısını ölçer. Trace hash ikisinin birlikte tekrarlanabilirliğini gösterir.
- Desteklenmeyen bir yapı sessizce yok sayılırsa ne tür hatalar oluşur?
  → Senaryo "SUCCESS" görünür ama test edilmek istenen manevra hiç çalışmamış olur; sonuç yanlış güven verir ve hata ancak sahada fark edilir. Bu yüzden desteklenmeyen düğüm derleme uyarısı + `FAILED` yaprak olarak yüzeye çıkar.
- Neden tek bir derleme süresi yerine dağılım raporluyoruz?
  → Parser'ın uyarlamalı tahmini içeriğe duyarlı; medyan, p95 ve min/max birlikte bakılmadan performans iddiası kurulamaz. Ayrıca ilk CARLA koşusunun ısınma etkisi ortalamayı bozar.

## Aşama 5.5 — Gerçek ASAM 2.2.0 kütüphanesi ve grammar farkı (tamamlandı)

**Kavram:** Normatif kaynak, bilgilendirici EBNF, sürüm farkı, mekanik diff, üst küme (superset), tanılama ile kapatılan boşluk.

**Yapılan:**
- ASAM 2.2.0 paketi `external/asam/` altına alındı: `grammar.ebnf`, `types.osc`, `domain.osc`, `standard.osc`. Lisans başlığı dağıtıma izin veriyor; dosyalar yine de `.gitignore` kapsamında.
- `grammar.ebnf` ↔ `openscenario2.g4` kural envanteri çıkarıldı: 165 EBNF, 154 parser + 16 lexer kuralı. 21 ad farkının yalnızca üçü davranışsal.
- Üç gerçek boşluk kapatıldı: enum üyesinin başka üyeye referansı (`truck = heavy_truck`), `range of` bildirimi, primitive `extend`.
- Kütüphanenin yüklenmesini engelleyen anlamsal hatalar giderildi (alan/tip gölgeleme, tipe göre enum çözümü, modifier/tip adı çakışması, yerleşik + gerçek kütüphane çakışması).
- `--stdlib external/asam/standard.osc` ile `standard.osc → domain.osc → types.osc` zinciri tanılamasız yükleniyor: 154 `std` + 112 `stdtypes` sembolü.

**Öğrenilen tuzaklar:**
- EBNF "bilgilendirici"dir; normative olan belgedir. Yine de kural adları ve alternatifler, uygulamanın nerede saptığını göstermede en ucuz araçtır.
- Ad farkı davranış farkı değildir: `sum`/`sum_exp` ya da `cast-exp`/`#cast_exp_pe` aynı dili anlatır. Karar için gerçek dosyayı ayrıştırmak gerekir.
- Proje bilinçli olarak üst kümedir: 2.2 `physical-literal` yalnızca tek `unit-name` alırken proje `m/s`, `m/s^2` kabul eder; top-level `use` 2.2'de kaldırılmış olsa da 2.1 hedefi için korunur.
- Tanılama sayısı tek başına başarı ölçüsü değildir: kütüphane "0 tanılama" verirken noktalı `action vehicle.drive` bildirimleri hedef tipe bağlanmıyor ve `hero.drive()` `W0105` alıyor. Sessiz boşluk, gürültülü hatadan daha tehlikelidir.

**Çıktı:** `osc2c check external/asam/standard.osc` → `ok`; `scenarios/asam/asam_stdlib.osc` gerçek kütüphaneye karşı yalnızca `W0102` ile geçiyor. Ayrıntı: [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md).

**Kendini test et:**
- Bilgilendirici EBNF ile normative spesifikasyon arasındaki fark ne; hangisine göre uyum iddia edilir?
- `m/s` desteği neden bir "eksik" değil de "üst küme"? Üst kümenin riski ne?
- Kütüphane tanılamasız geçerken hangi semantik boşluk görünmez kalıyor? Bunu nasıl görünür kılarsın?

## Aşama 5.6 — Nitelikli eylemlerin backend'de yürütülmesi (tamamlandı)

**Kavram:** Dağıtım sırası (dispatch), nitelikli eylem (`Actor.behavior`), bağlama (binding), `it` bağlamı, ortam modifier'ı, kayıt defteri (registry) eşlemesi, sessiz başarısızlık yerine gürültülü hata.

**Yapılan:**
- `X.behavior(...)` çözümü dört adımlı hale getirildi: `at: start` ile yükseltilen eylem → kullanıcı tanımlı gövde (kalıtımla gelen `do`/`on` dahil) → yöntem kayıt defteri (kütüphane eylemi yerel adla) → eşlenmemişse uyarı + `FAILED` yaprak.
- `ActionScope` (`backend/behaviors.py:53`) hedef aktörü `it` olarak bağlıyor; tick sırasında `context.it`, `context.locals` ve ortam modifier'ları geçici olarak değiştirilip `finally` ile geri yükleniyor.
- `_behavior_members` kalıtım zincirinde en yakın gövdeyi buluyor (`compiler.py:39`); parametre, varsayılan ve yerel değişken bağlama `_bind_action` (`compiler.py:491`) üzerinden action-call ile ortaklaştırıldı. `_build_attached_action` (`compiler.py:307`) özyineleme koruması taşıyor.
- Semantik katman, noktalı eylem gövdesinde `it`'i alıcı aktör olarak tipliyor (`builder.py:1187`, `_qualified_action_owner`); böylece `it.drive()` artık `W0105` almıyor.
- Standart kütüphane parametreleri yalnızca yorumlarda opsiyonel; `std`/`stdtypes` imzaları `_optional_signature` (`builder.py:185`) ile gevşetildi, geçerli `speed(10 mps)` çağrıları `E0405` vermiyor.
- Kayıt defterine `move`, `assign_speed`, `keep_speed`, `remain_stationary` eklendi (`method_registry.py:122`); `drive`/`walk` zaten eşlenmişti.
- Gövdesi olan nitelikli eyleme uygulanan standart `with:` modifier'ları çağrı anında değerlendiriliyor (`compiler.py:373`, `method_registry.py:78`) ve `ActionScope` boyunca ortam modifier'ı olarak taşınıyor. Gövdedeki `it` alıcılı kayıt defteri davranışları bu değerleri miras alıyor; iç `with:` aynı adı ezerse iç değer kazanıyor, farklı aktöre çağrıya değer sızmıyor (`behaviors.py:88`).
- Kullanıcı tanımlı modifier'lar bu aşamada genişletilmiyordu; her biri "user-defined and not applied" uyarısıyla raporlanıyordu. Bu boşluk Aşama 5.7'de kapatıldı.

**Öğrenilen tuzaklar:**
- "Semantik olarak doğrulandı" yürütüldü demek değildir: 0 tanılamalı kütüphane `hero.drive()` çağrısını çalıştırmıyordu.
- `it` hem tip düzeyinde hem runtime'da doğru olmalı; yalnızca birini düzeltmek hatayı bir katmandan diğerine taşır.
- Kütüphanedeki zorunlu/opsiyonel ayrımı yalnızca yorumlarda yazılı; katı imza doğru çağrıları reddetti. Gevşetme yalnızca standart ad alanlarıyla sınırlandı.
- Nitelikli eylem ile desteklenmeyen davranış ayrımı ağaçtan okunabilir: `ActionLeaf` (kayıt defteri) ile `UnsupportedLeaf` (eşlenmemiş).
- Eylem kendini çağırırsa sessiz sonsuz döngü yerine derleme zamanı hatası üretilmeli.
- "Doğrulandı" modifier'ın uygulandığı anlamına gelmez. Modifier, eylem gövdesine yalnızca alıcı `it` üzerinden ve yalnızca standart adlar için taşınmalı; aksi hâlde başka aktörün hızını değiştirmek gibi sessiz yan etkiler doğar.
- Dış modifier ile iç modifier çakışırsa iç kazanmalı: en yakın `with:` bloğu daha özgüldür.

**Çıktı:** `timer.hold(0.2 s)` → 0.2 s; `it.drive() with: speed(5 mps)` → hedef aktör 5 mps; `drive with speed(5 m/s)` → 5 m yol; `assign_speed` tek seferlik; `move` durative (1.2 m); `c.cruise() with: speed(5 mps)` → gövdedeki `it.drive()` 5 mps; iç `speed(3 mps)` dıştakini eziyor; `it` + başka aktör paralel sürerken yalnızca `it` 5 mps; `c.place() with: position(x: 10 m)` → x 10 m; eşlenmemiş `follow_trajectory` hâlâ `FAILED`. `scenarios/dev/qualified_action_modifiers.osc` → `SUCCESS`, 0.5 s, hız 5 m/s. `scenarios/asam/asam_stdlib.osc --stdlib` yalnızca `W0102`; `osc2c bt` çıktısı `hero.drive` ve `hero.assign_speed` için `ActionLeaf` gösteriyor. `pytest -q -m "not carla"` → 169 test (backend 59, semantics 64, frontend 27).

**Kendini test et:**
- Eylem çağrısı çözülürken hangi sıra izleniyor ve neden bu sıra?
  → Önce bir kez çalıştırılıp ağaçta `Success` olan `at: start` eylemleri, sonra kullanıcı tanımlı gövde, sonra kayıt defteri. Kullanıcı tanımı kütüphane eşlemesini gölgeler; eşlenmemiş ad ise sessizce geçmez.
- `it` neden yalnızca semantik katmanda değil runtime'da da bağlanmalı?
  → Semantik katman `it.drive()` çağrısının tipini denetler; çalışma zamanı ise gerçek aktör proxy'sini vermezse çağrı yanlış araca gider veya çöker.
- Dışarıdan verilen `with: speed(5 mps)` neden gövdedeki her davranışa değil, yalnızca `it` alıcılı olanlara uygulanıyor?
  → Modifier, eylemi alan aktörün fiziksel kısıtıdır. Gövde başka bir aktörü sürüyorsa aynı hız kısıtı ona ait değildir; aksi hâlde yan etki sessizce yayılır.
- İç ve dış modifier aynı adı taşırsa hangisi kazanmalı; neden?
  → İçteki kazanır; daha yakın kapsam daha özgül kabul edilir. Dış değer yalnızca içte belirtilmeyen alanlar için varsayılan işlevi görür.
- Standart kütüphane parametrelerini neden opsiyonel varsayıyoruz; bunun riski ne?
  → Ayrım yalnızca belge yorumlarında, yapısal bilgi yok. Risk, gerçekten zorunlu bir parametrenin atlanmasının derlemede yakalanmaması; bu yüzden gevşetme standart ad alanlarıyla sınırlı.
- Eşlenmemiş bir kütüphane eylemini sessizce yok saymak neden tehlikeli?
  → Senaryo `SUCCESS` görünür ama test edilmek istenen manevra hiç koşmamış olur.

## Aşama 5.7 — Kullanıcı tanımlı modifier genişletme (tamamlandı)

**Kavram:** Makro genişletme (macro expansion), düzleştirme (flattening), metinsel öncelik, döngü algılama, derleme zamanı ile çalışma zamanı değerlendirmesi ayrımı.

OSC2'de `modifier fast of vehicle: speed(10 mps)` bir çalışma zamanı nesnesi değil, bir **yeniden yazma kuralıdır**: `fast()` yazıldığı yerde `speed(10 mps)` yazılmış gibi davranmalıdır. Bu aşamaya kadar semantik katman `fast()` çağrısını çözüyor, backend ise onu tanımadığı için sessizce yutuyordu (yalnızca uyarı veriyordu). Aşama 5.7 bu boşluğu kapatır.

**Yapılan:**
- `src/osc2c/backend/modifiers.py` eklendi. `expand_behavior_with(model, with_clause)` bir `with:` bloğundaki uygulamaları alır; kullanıcı tanımlı modifier gövdesini özyinelemeli olarak standart `speed`/`lane`/`position` uygulamalarına düzleştirir.
- Genişletme **derleme zamanında** yapılır; argümanlar **çağrı anında** değerlendirilir. Böylece gövdedeki ifadeler `it` ve eylem yerelleri gibi çalışma zamanı bağlamını görebilir.
- Sıra korunur: `with:` içindeki uygulamalar ve modifier gövdeleri kaynak sırasıyla düzleştirilir; kayıt defteri sözlüğünde son uygulama öncekini ezer. `speed(5 mps)` sonra `fast()` → 10 mps; tersi → 5 mps.
- Döngü algılama, modifier adına değil `CompositeTypeInfo` kimliğine göre yapılır (`_stack`). `a → b → a` zinciri uyarı üretir ve genişletmeyi durdurur; sonsuz özyineleme yoktur.
- Yalnızca `ModifierApplication` üyeleri genişletilir. Gövdede `keep(...)`, `on` gibi başka bir üye varsa sessizce atlanmaz; uyarı üretilir. Açık hedefli (`actor.modifier(...)`) gövde uygulamaları da güvenli biçimde atlanır ve uyarılır.
- `compiler.py` genişletmeyi her davranış çağrısı için bir kez hesaplar. Doğrudan kayıt defteri çağrısı değerlendirilmiş modifier sözlüğünü `modifiers=` ile alır; gövdesi olan nitelikli eylemde aynı liste `ActionScope`'a taşınır ve gövdedeki `it` davranışlarına ortam modifier'ı olarak geçer.
- `method_registry.py` opsiyonel `modifiers` parametresi kazandı: hazır sözlük verilirse yeniden ayrıştırılmaz; miras alınan değerlerin üzerine kendi değerleri yazar.
- `initializer.py` de genişletmeyi kullanır: kullanıcı tanımlı modifier'ın gövdesindeki `at: start`, davranışın ilk tick'ten önce yükseltilmesini sağlar.
- `_ignored_feature_warnings` artık her kullanıcı modifier'ı için kör uyarı üretmez; yalnızca genişletilemeyen durumlar (çözülemeyen ad, döngü, desteklenmeyen gövde üyesi) raporlanır.

**Öğrenilen tuzaklar:**
- "Semantik olarak çözüldü" ile "çalışma zamanında uygulandı" aynı şey değildir. `model.resolved[id(app)]` yalnızca sembolü verir; onu standart bir uygulamaya çevirmek backend'in işidir.
- Genişletme sırasında uygulama listesini sözlüğe erken çevirmek öncelik hatası üretir. Önce sıralı liste, sonra sözlük; böylece "son yazan kazanır" kuralı korunur.
- Döngü algılamayı isimle yapmak yanlıştır: aynı ad farklı ad alanlarında farklı modifier'ları gösterebilir. Kimlik (`id(composite)`) kullanılmalıdır.
- Gövdedeki desteklenmeyen üyeleri sessizce atmak, projenin "sessiz yutma yok" politikasına aykırıdır. Kısmi genişletme yapılsa bile her atlanan üye uyarılmalıdır.
- Genişletmeyi hem derleme hem çalışma zamanında yapmak uyarıları çiftler. `_Builder` genişletmeyi bir kez, `registry.invoke` ise yalnızca değerlendirmeyi yapar.

**Çıktı:**
- `pytest -q -m "not carla"` → **169 passed**, 3 deselected (backend 59, semantics 64, frontend 27).
- Doğrudan davranış: `hero.drive() with: fast()` → hız 10 m/s.
- Nitelikli eylem gövdesi: `c.boost() with: fast()` → gövdedeki `it.drive()` hız 10 m/s.
- Sıra: `speed(5)` + `fast()` → 10; iç içe `very_fast → fast` → 10.
- Döngü: `a → b → a` → `cyclic user-defined modifier 'a'` uyarısı, senaryo yine de çalışır.
- `at: start`: `assign_position() with: start_fast()` → eylem ilk tick'ten önce uygulanır (`initialized_actions` dolu), hız 5 m/s.
- Eski "user-defined and not applied" uyarısı kaldırıldı; `cover(...)`/`record(...)` uyarıları değişmedi.

**Kendini test et:**
- Kullanıcı tanımlı modifier neden çalışma zamanında değil derleme zamanında düzleştiriliyor?
  → Çünkü dil semantiği bir yeniden yazma kuralıdır; çalışma zamanında her tick'te gövdeyi yeniden yorumlamak gerekir ve öncelik/döngü hataları geç fark edilir. Derleme zamanı düzleştirme, kayıt defterinin zaten bildiği standart uygulamalara indirger; argüman değerlendirmesi ise çağrı anında kalır.
- `speed(5)` sonra `fast()` neden 10 veriyor, tersi neden 5?
  → Çünkü genişletme kaynak sırasını korur ve sözlük güncellemesinde son anahtar kazanır. Bu, OSC2'nin "daha sonraki uygulama daha özgül/ezer" davranışının doğal sonucudur.
- Döngüyü isimle değil kimlikle algılamanın farkı nedir?
  → Aynı kısa ad farklı ad alanlarında farklı tanımlara çözülebilir; isimle kontrol yanlış pozitif/negatif verir. Kimlik, gerçek bildirim düğümünü izler.
- Genişletme neden `ActionScope` içinde değil de derleme sırasında yapılıyor?
  → `ActionScope` her tick'te çalışır; genişletme ise AST'nin statik bir dönüşümüdür. Ağacı kurarken bir kez yapmak hem daha hızlı hem de uyarıları tekilleştirir. `ActionScope` yalnızca değerlendirilmiş değerleri taşır.

## Aşama 6 — Tez

**Kavram:** Araştırma sorusu, katkı, sınırlılık, tehditler, tekrarlanabilirlik.

**Yapılacak:**
- RQ1–RQ3 etrafında sonuçları düzenle.
- Katkıyı netleştir: açık kaynak reprodüksiyon + mock backend + ölçüm.
- Sınırlılıkları dürüstçe yaz (kapsam, performans, standart dosyaları).
- Demo ve savunma provası.

**Kendini test et:**
- "Makaleyi yeniden yazdım" ile "makaleyi doğruladım ve ölçtüm" arasındaki fark ne?
- Tezin özgün katkısı hangi tek cümleyle anlatılır?
- Hangi sonuç olmasaydı proje başarısız sayılırdı?
