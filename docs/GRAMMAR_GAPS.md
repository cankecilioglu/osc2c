# Grammar 2.1 Fark Analizi — 26 Ekim 2026

Bu belge, projenin kullandığı OpenSCENARIO grammar'ının hangi dil yapılarını
uçtan uca kabul ettiğini, hangilerini yalnızca sözdizimsel olarak tanıyıp
anlamsal veya çalışma zamanı katmanında reddettiğini ve hangi 2.1 alanlarının
henüz karşılanmadığını kaydeder. Amaç eksiksiz bir dil uyumluluğu iddiası
kurmak değil; her farkı gözlenebilir çıktı, tanılama kodu veya testle
izlenebilir kılmaktır.

## 1. Kapsam ve yöntem

İnceleme üç kaynak üzerinden yürütüldü:

1. **Vendored grammar:** [`grammar/openscenario2.g4`](../grammar/openscenario2.g4)
   (333 satır). Dosya başlığındaki MPL-2.0 bildirimi korunur; üretilen parser
   `scripts/generate_parser.py` ile ANTLR 4.13.2 kullanılarak yeniden üretilir.
2. **Küçük kaynak denemeleri:** Her yapı `parse` → `analyze` → `compile` →
   `run` zincirinden geçirildi. Tanılama kodları ve çalışma zamanı sonuçları
   doğrudan bu çıktılardan alındı; tahmin edilmedi.
3. **Mevcut testler:** [`tests/test_frontend_ast.py`](../tests/test_frontend_ast.py),
   [`tests/test_semantics.py`](../tests/test_semantics.py) ve
   [`tests/test_backend.py`](../tests/test_backend.py) içindeki golden,
   pozitif ve negatif testler.

**Güncelleme (27 Ekim 2026):** ASAM 2.2.0 paketi (`grammar.ebnf`, `types.osc`,
`domain.osc`, `standard.osc`) artık `external/asam/` altında yerel olarak
mevcut ve tümü ayrıştırılıp anlamsal olarak denetlendi. Paket başlığı
dağıtıma izin verse de dosyalar `.gitignore` kapsamında tutuluyor. EBNF ↔
proje grammar karşılaştırması, kapatılan boşluklar ve kalan sapmalar ayrı
belgede kayıtlıdır: [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md). Bu belgedeki
kapsam değerlendirmeleri hâlâ geçerlidir; yalnızca "resmî kütüphane yok"
varsayımına dayanan ifadeler aşağıda güncellenmiştir.

## 2. Özet

| Katman | Durum |
|---|---|
| Sözdizimi (lexer/parser) | Yaklaşık 70 AST düğümü; bildirimler, ifadeler, olaylar ve kompozisyonların büyük bölümü ayrıştırılıyor |
| Anlamsal orta uç | Kapsam, tip, SI birim, enum, kalıtım ve argüman denetimi çalışıyor |
| Çalışma zamanı / BT | `serial`, `parallel`, `one_of`, `wait`, `emit`, `until`, süreli sürüş ve yerleşim çalışıyor |
| Resmî standart kütüphane | 2.2.0 paketi `external/asam/` altında mevcut; `--stdlib` ile yükleniyor, tanılamasız geçiyor. Depoda izlenmiyor; `external/` yoksa yerleşik alt küme devreye girer |
| Kapsam matrisi | 43 satır: 24 destekli, 10 kısmi, 9 desteklenmiyor (katı %56, ağırlıklı %67) |

Test sayısı: **169 CARLA'sız + 3 CARLA = 172**. Bu sayı yeni eklenen
`until`, `sample`, `remove_default`, `cover/record`, kullanıcı modifier'ı,
`=>`, eylem çağrısı (gövde, argüman, aktör parametresi, iç içe çağrı,
özyineleme), nitelikli eylem (bağlama, gövde yürütme, parametre/`it`,
özyineleme), nitelikli eylemde standart modifier aktarımı (gövdeye ulaşma,
iç içe geçersiz kılma, alıcı izolasyonu, konum), kullanıcı tanımlı modifier
genişletme (doğrudan davranış, eylem gövdesi, sıra, iç içe, döngü, `at: start`),
bileşik birim (pozitif, negatif ve runtime)
ve gerçek ASAM kütüphanesi (enum takma adı, `range of`, primitive `extend`,
kütüphane eylemi yürütme ve `--stdlib` CLI çalıştırması) testlerini içerir.

## 3. Uçtan uca desteklenen dil

Aşağıdaki yapılar ayrıştırılıyor ve anlamsal olarak denetleniyor. Tabloda
listelenen çalıştırılabilir yapılar mevcut backend tarafından en az bir
adaptörde uygulanıyor; kullanıcı tanımlı `modifier` gövdeleri standart
uygulamalara düzleştirilerek uygulanıyor, ancak action kalıtımında yalnızca
en yakın tabanın gövdesi alınıyor. Bu tür yarı-destekli yapılar bölüm 5'te
ayrıca listelenir.

| Alan | Desteklenen yapılar | Kanıt |
|---|---|---|
| Ön bilgi | `import "dosya"`, `use a.b, c.d`, `namespace`, `export` | `test_cli_loads_relative_imports`, `test_qualified_names_and_ambiguous_namespaces` |
| Bildirimler | `type`, `unit`, `enum`, `extend enum`, `struct`, `actor`, `scenario`, `action`, `modifier`, `global`, `def` | `scenarios/dev/grammar_tour.osc`, `test_inherited_fields_and_enum_extension` |
| Kalıtım | Actor/struct tip alanları, metotlar ve enum genişletmeleri | `test_inheritance_cycle_and_kind_mismatch`, `test_inherited_fields_and_enum_extension` |
| Tipler | `int`, `uint`, `float`, `bool`, `string`, `list of T`, fiziksel tipler | `test_unit_registry_and_conversions` |
| Birimler | SI boyutları, özel `type`/`unit`, `factor` ve `offset` | `test_inherited_fields_and_enum_extension`; `m`, `km`, `mph`, `kph`, `mps`, `deg`, `ms` |
| Bileşik birimler | `m/s`, `km/h`, `m/s^2`; `/` ve `^`, SI boyut ve faktör türetimi | `scenarios/dev/compound_units.osc`, `test_compound_units_resolve_and_convert`, `test_compound_unit_literals_evaluate_to_si` |
| İfadeler | Aritmetik, karşılaştırma, `and`/`or`/`not`, `=>`, üçlü operatör, `in`, liste, aralık, alan/eleman erişimi, `.as(...)`, `.is(...)` | `test_implication_is_evaluated`; üçlü operatör ve cast probe ile doğrulandı |
| Kompozisyon | `serial`, `parallel`, `one_of`, etiketli ifade | `test_serial_parallel_and_one_of_mapping` |
| Eylem çağrıları | `call action(...)`, konumsal/adlandırılmış argüman, varsayılan, aktör parametresi, iç içe çağrı | `scenarios/dev/action_calls.osc`, `test_action_call_binds_arguments`, `test_nested_action_calls_restore_the_caller_scope` |
| Davranış | `drive`, `walk`, `change_speed`, `change_lane`, `assign_position`, `set_lights`, `assign_celestial_position` | `test_pedestrian_walk_moves_actor`, `test_cut_in_scenario_runs_on_carla` |
| Değiştiriciler | `speed`, `lane`, `position` | `scenarios/dev/lane_change_speed.osc`, `placement_modes.osc` |
| Olaylar | `elapsed`, `rise`, `fall`, `@event`, `emit`, kenar algılama | `test_rise_does_not_fire_on_an_already_true_condition`, `test_fall_edge_fires_after_speed_drops` |
| Sonlandırma | `until` ile süreli davranışı kesme | `test_until_terminates_durative_behaviour` |
| Kısıtlar | `keep(it.<alan> == değer)` | `test_keep_constraints_bind_actor_attributes` |
| Başlangıç | `at: start` yerleşimleri, üç yerleştirme modu | `tests/test_carla.py`, `placement_modes.osc` |

`until`, `behavior_with_declaration` içinde (`with:` altında) bir olay
belirtimi olarak tanımlıdır; tekil `do` komutu değildir
([grammar/openscenario2.g4:230](../grammar/openscenario2.g4#L230)). Backend
bunu süreli davranış ile bir `WaitLeaf`'i `Parallel(SuccessOnOne)` içinde
birleştirerek uygular
([src/osc2c/backend/compiler.py:391](../src/osc2c/backend/compiler.py#L391)).

## 4. Grammar kabul ediyor, anlamsal katman reddediyor

Bu gruptaki yapılar sözdizimsel olarak geçerlidir; ancak tip/birim çözümü
veya ilgili sembol bulunamadığı için kararlı bir tanılama kodu üretilir.
Hata seviyesindeki tanılamalar derlemeyi durdurur; uyarılar derlemeyi
sürdürür.

| Kullanım | Gözlenen sonuç | Neden |
|---|---|---|
| `var v : speed = 1 m/parsec` | `E0203 unknown unit 'parsec'` | Bileşik birim ifadesi ayrıştırılıyor; her bileşen kapsamda birim olarak çözülüyor |
| `var t : temp = 1 celsius/K` | `E0203 unit 'celsius' has an offset ...` | Offset'li birimler bileşik birimde çarpımsal dönüşüme uygun değil |
| `box : stationary_object` | `E0201 unknown type 'stationary_object'` | Yerleşik fallback standart kütüphanesinde tanım yok ([stdlib.py](../src/osc2c/semantics/stdlib.py)) |
| `m : map` | `E0201 unknown type 'map'` | Aynı neden; harita tipi ve yol semantiği yok |
| `rate_profile(linear: 1 mps)` | `W0104 unknown modifier 'rate_profile'` | Fallback kütüphanesinde değiştirici tanımı yok; hız profili backend'de de yok |
| `object_distance(hero, other)` | `E0402 unknown method or behavior` | Fallback kütüphanesinde yöntem yok; mevcut API `position.ahead_of()` / `position.euclidean()` |
| `var xs : list of int = range(1, 3)` | `E0401 initial value expects list of int, got range of int` | Aralık tipi listeye atanabilir değil; çalışma zamanı aralığı listeye açabiliyor ama tip sistemi bunu kabul etmiyor |
| `!cond`, `a && b` | Parse/token hatası | Kanonik yazım `not`, `and`, `or`; `!` yalnızca `enum!üye` içinde kullanılır |

**Gerçek 2.2.0 kütüphanesiyle ölçüm (27 Ekim 2026):** `stationary_object` ve
`map` artık çözülüyor; kalan tek tanılama senaryodaki tanımsız olaydır
(`W0102`). `rate_profile` bir değiştirici değil, `dynamic_profile` tipli bir
parametredir (`domain.osc:1155`), bu yüzden çağrı biçiminde `E0404` alınır.
`object_distance` ise `physical_object` üzerinde tanımlı bir `def`'tir
(`domain.osc:358`); senaryo gövdesinde niteliksiz çağrılamadığı için `E0402`
verir — kütüphane eksikliği değil, çağrı bağlamı sınırıdır. Bileşik birimler
(`m/s`, `m/s^2`) grammar, anlamsal katman ve çalışma zamanında destekleniyor;
kalan sınırlar bölüm 6'da listelenir.

## 5. Grammar ve anlamsal katman kabul ediyor, backend uygulamıyor

Bu yapılar derlenebilir; fakat çalışma zamanındaki etkileri eksik veya yoktur.
Sessiz yutmayı önlemek için mümkün olan her yerde derleme uyarısı üretilir.

| Yapı | Güncel davranış | Eksik |
|---|---|---|
| `greet()` (hedefsiz davranış çağrısı) | `CompilationError: behaviour 'greet' has no target` | Anlamsal katman senaryo/action sembolünü çözüyor; backend hedefsiz çağrıyı derlemiyor; `call greet()` çalışıyor |
| `call hero.drive()` | Derlenir; sürüş başlamaz, `CallLeaf` ifadeyi değerlendirip `None` alır | Yöntem çağrısı ile davranış çağrısı ayrımı net değil; `drive` bir davranış, ifade yöntemi değil |
| Kullanıcı tanımlı modifier (`modifier fast of vehicle: speed(...)`) | Derlenir; gövdesi standart uygulamalara düzleştirilip uygulanır | Yalnızca `ModifierApplication` üyeleri genişletilir; `keep`/`on` gibi diğer üyeler uyarıyla atlanır, döngü algılanır |
| `on @event:` | `UnsupportedLeaf` → `FAILURE`, `unsupported` listesine yazılır | Olay güdümlü dallanma backend'de yok ([compiler.py:541](../src/osc2c/backend/compiler.py#L541)) |
| `cover(...)`, `record(...)` | Derlenir; hiçbir kayıt üretilmez | Uyarı eklenir; kapsam/iz kaydı entegrasyonu yok |
| `sample(expr, @event, default)` | Değişken için varsayılan değer kullanılır | Uyarı: örnekleme değerlendirilmiyor; yalnızca `default` atanıyor ([context.py:117](../src/osc2c/runtime/context.py#L117)) |
| `remove_default(...)` | Yoksayılır | Artık iç içe geçmişler dahil uyarı üretir; varsayılan kaldırma uygulanmıyor |
| `wait every(200 ms)` | Bir kez `SUCCESS` olur | Periyodik olay yeniden tetiklenmiyor; `WaitLeaf` başlangıç zamanını sıfırlıyor ama tek seferlik tamamlıyor |
| `scenario child inherits base` | Alt senaryonun kendi `do` gövdesi çalışır; alanlar miras alınır | Taban senaryonun `do`/`on` davranışları birleştirilmiyor (denemede yalnızca `CHILD` üretildi) |
| Desteklenmeyen davranış (`fly()`) | Derleme uyarısı + `FAILURE` yaprak | Kasıtlı ve gürültülü davranış |
| Desteklenmeyen `keep` biçimi | Derleme uyarısı; kısıt doğrulanır ama uygulanmaz | Yalnızca `keep(it.<alan> == değer)` uygulanıyor |
| Bilinmeyen ışık modu | `ValueError` | Sessiz `NONE` yerine açık hata |

## 6. Lexer ve sözdizimi biçim kısıtları

Aşağıdakiler hata değil, dilin mevcut yazım kurallarıdır; senaryo yazarken
bilinmesi gerekir:

- **Girinti duyarlıdır.** Bloklar `:` + `INDENT`/`DEDENT` ile kurulur;
  `do serial` gibi iki nokta eksik yazımlar ayrıştırılamaz.
- **Bileşik birimler `/` ve `^` ile yazılır.** `m/s`, `km/h`, `m/s^2` ve
  negatif üsler (`m/s^-2`) desteklenir
  ([satır 321-322](../grammar/openscenario2.g4#L321)). Operatörler soldan
  sağa uygulanır. `*` bileşik birim çarpanı olarak desteklenmez; `kg*m/s^2`
  ayrıştırılamaz, bunun yerine tanımlı bir alias (`N` gibi) veya ayrı
  çarpma ifadesi kullanılmalıdır.
- **Birim ifadesi çarpma bölmeyle karışabilir.** `1 m / x` yazımı, `x`
  değişken olsa bile birim ifadesi olarak ayrıştırılır ve `x` birim değilse
  `E0203` üretir. Uzunluğu değişkene bölmek için `(1 m) / x` yazımı
  kullanılmalıdır.
- **`namespace` iki nokta istemez.** Doğru yazım `namespace demo`; yanlış
  yazım `namespace demo:` ayrıştırma hatası verir.
- **`action` ve `modifier` gövdeleri farklıdır.** `action a:` gövdesi
  senaryo üyeleri ve davranış belirtimleri alır; `modifier m of vehicle:`
  gövdesi senaryo üyeleri ve `on` direktifleri alır, tekil `do` almaz
  ([satır 123-132](../grammar/openscenario2.g4#L123)).
- **Yalnızca tek `::` desteklenir.** `prefixed_identifier` bir ad alanı
  öneki + yerel ad biçimindedir; `std::stdtypes::speed` doğrudan yazılamaz.
  Çözüm: `use stdtypes` + kısa ad veya `--stdlib`.
- **`export` ve `import` çözümlemesi sınırlıdır.** Göreli dosya import'ları
  özyinelemeli yüklenir; ad alanı import'ları dosya yüklemez, yalnızca
  görünürlük kaydı oluşturur.
- **`enum` üyeleri çıplak ad olarak yazılabilir**; sözdizimsel olarak
  değişken adıyla aynı görünür. Ayrım anlamsal çözümlemede yapılır; aynı ad
  iki enum'da varsa `E0404` belirsizliği oluşur.

## 7. Resmî standart kütüphanesi ve yerleşik yedek

İki mod vardır:

- **Gerçek kütüphane:** `--stdlib external/asam/standard.osc`. CLI,
  `standard.osc` → `domain.osc` → `types.osc` import zincirini özyinelemeli
  yükler; toplam 154 `std` + 112 `stdtypes` sembolü çözülür ve tanılama
  üretilmez. Yerleşik alt küme otomatik olarak devre dışı kalır.
- **Yerleşik yedek:** `--stdlib` verilmezse
  [`src/osc2c/semantics/stdlib.py`](../src/osc2c/semantics/stdlib.py) içindeki
  alt küme kurulur. Bu mod, depo `external/` olmadan da testlerin ve
  senaryoların çalışmasını sağlar.

Yerleşik alt kümenin içeriği:

- Fiziksel tipler: `length`, `distance`, `speed`, `acceleration`, `time`,
  `angle`, `mass`, `temperature`, `electric_current`, `amount_of_substance`,
  `luminous_intensity`, `frequency`, `force`, `energy`.
- Birimler: `m`, `km`, `cm`, `mm`, `s`, `ms`, `min`, `h`, `rad`, `deg`,
  `mps`, `kph`, `mph`, `kg`, `g`, `K`, `A`, `mol`, `cd`.
- Aktörler: `traffic_participant`, `vehicle`, `pedestrian`, `environment`.
- Yapılar/yöntemler: `position` (`ahead_of`), araç (`drive`,
  `assign_position`), yaya (`walk`), çevre (`assign_celestial_position`).
- Değiştiriciler: `speed`, `lane`, `position`; enum'lar: `direction`, `side`.

Sonuçları:

- Tanımsız dış olaylar `W0102`, tanımsız dış yöntemler `W0105` uyarısı verir.
  Bunlar hata değildir. Gerçek `domain.osc` yüklendiğinde `W0102` yalnızca
  senaryonun kendi tanımlamadığı olaylar için kalır.
- `stationary_object`, `map` gibi adlar yerleşik alt kümede yoktur (`E0201`);
  gerçek kütüphanede çözülürler. `rate_profile` ve `object_distance` için
  gözlenen `E0404`/`E0402` kütüphane eksiği değil, çağrı biçimi/bağlamı
  sınırıdır (bölüm 4).
- `--stdlib` gerçek 2.2.0 paketiyle doğrulandı:
  `osc2c check external/asam/standard.osc` → `ok` (exit 0) ve
  `scenarios/asam/asam_stdlib.osc` → yalnızca `W0102` (exit 0). Ayrıntı ve
  kapatılan üç sözdizimi boşluğu: [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md).
- **Noktalı davranışlar bağlanıyor ve yürütülüyor:** `action vehicle.drive`
  gibi 48 bildirim hedef aktörün yöntem tablosuna ekleniyor; `hero.drive()`
  ve `hero.assign_position()` tanılamasız çözülüyor, taban aktörün eylemleri
  kalıtımla görünüyor. Backend gövdesi olan kullanıcı eylemlerini derliyor,
  `it`'i hedef aktöre bağlıyor; gövdesiz kütüphane eylemlerini simülatör
  kayıt defterine düşürüyor (`move`, `assign_speed`, `keep_speed`,
  `remain_stationary` bu geçişte eklendi). Eşlemesi olmayan eylem uyarı +
  `FAILURE` üretmeye devam ediyor. Kütüphane eylemlerinde ve standart
  modifier'larda eksik argüman hata sayılmıyor (zorunlu/isteğe bağlı bilgisi
  yalnızca yorumda); sağlanan argümanın adı ve tipi denetleniyor. Ayrıntı:
  [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §6.
- `external/asam/` `.gitignore` kapsamında olduğu için gerçek kütüphaneye
  bağlı testler başka bir klonda `skipif` ile atlanır.

## 8. Bu geçişte düzeltilenler

1. **`until` uygulandı.** Süreli davranış `Parallel(SuccessOnOne)` ile
   sonlandırılıyor; `until elapsed(500 ms)` testi sürüşün 5 m'de durduğunu
   doğruluyor ([test_backend.py:218](../tests/test_backend.py#L218)).
2. **`sample(...)` sessiz kalmıyor.** Varsayılan değer kullanılıyor ve
   derleme uyarısı üretiliyor.
3. **`remove_default` uyarısı derinleştirildi.** Artık yalnızca senaryo
   üstünde değil, iç içe `with:` bloklarında da raporlanıyor.
4. **`cover`/`record` raporlanıyor.** Backend'in uygulamadığı bu yapılar
   derleme uyarısına dönüştü. Kullanıcı tanımlı modifier'lar artık
   uygulanıyor; bkz. madde 15.
5. **Eylem gövdeleri derlendi.** `call action(...)` artık action bildiriminin
   `do`/`on` ağacını kapsamlı bir alt ağaç olarak çalıştırıyor. Argümanlar
   konumsal veya adlandırılmış olarak çağrı anında bağlanıyor, eksik
   parametreler varsayılandan geliyor ve action içi `var`'lar her çağrıda
   yeniden kuruluyor. Kapsam çağrı sonunda geri yükleniyor; iç içe çağrılar
   çağıranın yerellerini bozmuyor. Eksik argüman `E0405`, bilinmeyen adlı
   argüman `E0406`, öz yineleme derleme hatası veriyor
   ([compiler.py:447](../src/osc2c/backend/compiler.py#L447),
   [behaviors.py:53](../src/osc2c/backend/behaviors.py#L53)).
6. **Mantıksal gerektirme (`=>`) çalışma zamanında uygulandı.** Daha önce
   geçerli bir ifade `EvaluationError` ile derlemeyi çökertiyordu
   ([context.py:470](../src/osc2c/runtime/context.py#L470)).
7. **Kapsam matrisi ve kanıt doğrulaması** önceki denetimde
   güçlendirilmişti; bu geçişte matrise yeni satır eklenmedi.
8. **Bileşik birimler uygulandı.** Grammar'a `unit_expression` ve `unit_term`
   kuralları eklendi; `m/s`, `km/h` ve `m/s^2` ayrıştırılıyor. Anlamsal
   katman bileşenleri çözüp SI boyutunu ve faktörünü türetiyor, runtime
   değeri SI'ya çeviriyor. Bilinmeyen bileşen `E0203`, offset'li bileşen
   yine `E0203` ile reddediliyor
   ([builder.py:1460](../src/osc2c/semantics/builder.py#L1460)).
9. **Enum üyesi başka üyeye referans verebiliyor.** `enum-member-value`
   artık `uint-literal | hex-uint-literal | enum-value-reference` kabul eder.
   `domain.osc` içindeki `truck = heavy_truck` takma adı böylece ayrıştırılıp
   değeri kopyalanıyor; bilinmeyen referans `E0103` veriyor
   ([builder.py:518](../src/osc2c/semantics/builder.py#L518)).
10. **`range of` bildirimi.** `list of range of int` gibi iç içe aralık
    tipleri ayrıştırılıp `RangeTypeInfo` olarak çözülüyor
    ([builder.py:1576](../src/osc2c/semantics/builder.py#L1576)).
11. **Primitive `extend`.** `extend float:` biçimi ayrıştırılıyor; metotlar
    kaydediliyor ancak çalıştırılmadıkları için `W0106` ile raporlanıyor.
12. **Gerçek kütüphane tanılamasız yükleniyor.** `types.osc`, `domain.osc` ve
    `standard.osc` birlikte ayrıştırılıp çözümleniyor; ayrıntı
    [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md).
13. **Noktalı eylemler aktöre bağlanıyor.** `_attach_qualified_actions`,
    `action A.b` bildirimlerini `A.methods` tablosuna ekliyor. Kütüphanedeki
    48 nitelikli eylem artık `hero.drive()` gibi çağrılarda çözülüyor ve
    taban aktör eylemleri kalıtımla görünüyor. Argüman tipleri denetlenmeye
    devam ediyor; kütüphane eylemlerinde zorunlu/isteğe bağlı ayrımı yalnızca
    yorumlarda yazdığı için eksik argüman `E0405` üretmiyor
    ([builder.py:904](../src/osc2c/semantics/builder.py#L904)).
14. **Bağlanan eylemler backend'de yürütülüyor.** Gövdesi olan
    `action A.b` bildirimleri davranış ağacına derleniyor; parametreler,
    yerel `var`'lar ve `it` (hedef aktör) çağrı anında bağlanıyor, taban
    eylemin `do` gövdesi miras alınıyor
    ([compiler.py:307](../src/osc2c/backend/compiler.py#L307),
    [behaviors.py:53](../src/osc2c/backend/behaviors.py#L53)). Gövdesiz
    kütüphane eylemleri kayıt defterindeki karşılıklarına düşüyor; bu
    geçişte `move`, `assign_speed`, `keep_speed` ve `remain_stationary`
    eklendi ([method_registry.py:122](../src/osc2c/backend/method_registry.py#L122)).
    Eşlemesi olmayan eylem (`follow_trajectory` gibi) uyarı + `FAILURE`
    üretmeye devam ediyor. Standart kütüphane modifier'larının parametreleri
    de isteğe bağlı sayılıyor; böylece `hero.drive() with: speed(10 mps)`
    gerçek kütüphaneyle çalışıyor
    ([builder.py:185](../src/osc2c/semantics/builder.py#L185)).
15. **Standart modifier'lar nitelikli eylem gövdesine aktarılıyor.**
    `c.cruise() with: speed(5 mps)` çağrısında modifier çağrı anında
    değerlendirilip `ActionScope` boyunca ortam modifier'ı olarak tutuluyor;
    gövdedeki `it` alıcılı yerleşik davranışlar (`drive`, `assign_position`,
    ...) değeri miras alıyor. İç `with:` aynı adı ezerse iç değer kazanıyor,
    farklı aktöre yapılan çağrıya değer sızmıyor
    ([compiler.py:373](../src/osc2c/backend/compiler.py#L373),
    [behaviors.py:88](../src/osc2c/backend/behaviors.py#L88),
    [method_registry.py:78](../src/osc2c/backend/method_registry.py#L78)).
    Kullanıcı tanımlı modifier'lar da `backend/modifiers.py` ile derleme
    zamanında düzleştiriliyor; gövdedeki standart uygulamalar doğrudan
    davranışlara, nitelikli eylem gövdelerine ve `at: start` yükseltmesine
    aktarılıyor. Döngü ve desteklenmeyen gövde üyeleri uyarıyla raporlanıyor
    ([modifiers.py](../src/osc2c/backend/modifiers.py)).

## 9. Kalan işler ve öncelik

| Öncelik | İş | Neden / sonraki adım |
|---|---|---|
| — (kapandı) | ASAM 2.2.0 grammar ve kütüphanesi ile mekanik diff | Tamamlandı: 165 EBNF / 154 parser kuralı karşılaştırıldı, üç boşluk kapatıldı — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) |
| — (kapandı) | Noktalı davranış adlarını hedef tipe bağla | `_attach_qualified_actions` 48 kütüphane eylemini aktörün yöntem tablosuna ekliyor; `hero.drive()` artık çözülüyor — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §6 |
| — (kapandı) | Bağlanan eylemleri backend'de yürüt | Gövdeli eylemler derleniyor, `it` hedef aktöre bağlanıyor; `move`, `assign_speed`, `keep_speed`, `remain_stationary` kayıt defterine eklendi; eşlemesi olmayan eylem uyarı + `FAILURE` — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §6.1 |
| P1 | `external/asam/` repoya alınsın mı? | Lisans dağıtıma izin veriyor; karar verilirse `NOTICE` güncellenip `skipif` testleri her klonda çalışır — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §8 |
| P1 | Senaryo kalıtımında davranış birleştirme | Taban `do`/`on` üyeleri alt senaryoya taşınmalı; alanlar zaten miras alınıyor |
| — (kapandı) | Kullanıcı tanımlı modifier genişletme | Gövde uygulamaları derleme zamanında düzleştiriliyor; doğrudan davranış, nitelikli eylem ve `at: start` yollarında uygulanıyor; döngü ve desteklenmeyen üyeler uyarılıyor — [`STAGES.md`](STAGES.md) §Aşama 5.7 |
| — (kapandı) | Gövdesi olan eyleme uygulanan `with:` modifier'ları | Standart `speed`/`lane`/`position` modifier'ları gövdedeki `it` davranışlarına aktarılıyor; iç modifier dıştakini eziyor. Kullanıcı tanımlı modifier genişletme de Aşama 5.7'de tamamlandı — [`STAGES.md`](STAGES.md) §Aşama 5.7 |
| P2 | Bağlı eylemlerde `at: start` | Başlangıç yerleşimi yalnızca kayıt defterindeki adlar için önceden uygulanıyor |
| P2 | `on` direktifleri | Olay güdümlü dallar BT'ye bağlanmalı; şu anda gürültülü `FAILURE` |
| P2 | `every` periyodikliği | Her periyotta yeniden tetiklenen olay semantiği; şu anda tek seferlik |
| P2 | `cover`/`record` entegrasyonu | Kapsam ölçümü ve trace kaydı; şu anda yalnızca uyarı |
| P2 | `*` içeren bileşik birimler (`kg*m/s^2`) | `*` grammar'a eklenirse `1 m * x` çarpımıyla belirsizlik doğar; ayrım kuralı veya tanımlı alias gerekli |
| P3 | `call` ile davranış çağrısı ayrımı | `call hero.drive()` gibi ifadelerde yöntem/davranış ayrımı netleştirilmeli |
| P3 | `range` → `list` atanabilirliği | Tip sisteminde aralık/liste uyumu veya açık dönüşüm |
| P3 | Action içi aktör tipli yerel değişkenler | Gövdeler taban eylemden miras alınıyor, ancak action içinde bildirilen aktör tipli yerel değişkenler spawn edilmiyor |
| P3 | `call scenario(...)` | Senaryo çağrısı yalnızca uyarı veriyor; iç içe senaryo yürütme yok |

## 10. Yeniden üretim

```bash
cd C:\Users\canke\Desktop\osc2-carla
.venv\Scripts\python.exe -m pytest -q -m "not carla"
.venv\Scripts\python.exe -m pytest -q -m carla
.venv\Scripts\python.exe -m compileall -q src

# Bileşik birim: geçerli senaryo ve kasıtlı hata
.venv\Scripts\osc2c.exe check scenarios\dev\compound_units.osc
.venv\Scripts\osc2c.exe check scenarios\diagnostics\unknown_compound_unit.osc

# Eylem çağrıları: parametre, varsayılan ve aktör bağlama
.venv\Scripts\osc2c.exe check scenarios\dev\action_calls.osc
.venv\Scripts\osc2c.exe run scenarios\dev\action_calls.osc --ticks 50

# Nitelikli eylemde with: modifier aktarımı (gövdeye speed + position)
.venv\Scripts\osc2c.exe check scenarios\dev\qualified_action_modifiers.osc
.venv\Scripts\osc2c.exe run scenarios\dev\qualified_action_modifiers.osc --ticks 30

# Gerçek ASAM 2.2.0 kütüphanesi (external/asam yoksa atlanır)
.venv\Scripts\osc2c.exe check external\asam\standard.osc
.venv\Scripts\osc2c.exe check scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc

# Grammar'ı yeniden üretme (MPL-2.0 bildirimi korunur; JDK 17 veya 21 gerekir)
.venv\Scripts\python.exe scripts\generate_parser.py
```

Beklenen: **169 CARLA'sız + 3 CARLA testi** yeşil. `check` çıktıları:

```text
scenarios\dev\compound_units.osc: ok
unknown_compound_unit.osc:5:20: error[E0203]: unknown unit 'parsec'
```

`action_calls.osc` iki `W0102` uyarısı verir (`READY`, `DONE` dış olay
olarak tanımlı değil); bunlar hata değildir. `run` çıktısı:

```text
status: SUCCESS, ticks: 3, time: 0.2
events: READY, DONE
hero: s = 0.5 m, speed = 5 m/s
```

`qualified_action_modifiers.osc` yalnızca `DONE` için `W0102` verir;
`c.cruise()` gövdesi dışarıdan `speed(5 mps)` alır, `c.place()` gövdesi
`position(x: 10 m)` alır. `run` çıktısı:

```text
status: SUCCESS, ticks: 6, time: 0.5
events: DONE
c: speed = 5 m/s
```

Gerçek kütüphane çıktıları:

```text
external\asam\standard.osc: ok

asam_stdlib.osc:17:8: warning[W0102]: unknown event 'DONE'; external domain definition not loaded
```

Gerçek kütüphane testleri: `test_asam_standard_library_parses`,
`test_asam_standard_library_has_no_diagnostics`,
`test_scenario_compiles_against_the_real_standard_library`,
`test_qualified_action_binds_to_the_actor`,
`test_qualified_action_checks_argument_types`.
Yeni sözdizimi testleri: `test_enum_member_value_may_reference_another_member`,
`test_enum_member_reference_copies_the_value`,
`test_unknown_enum_member_reference_is_reported`,
`test_range_type_declarators_parse`,
`test_range_declarator_resolves_to_a_range_type`,
`test_primitive_type_extension_parses`,
`test_primitive_type_extension_is_reported_as_unexecuted`,
`test_field_may_share_a_name_with_a_type`,
`test_modifier_and_type_may_share_a_name`.

Bileşik birim testleri: `test_compound_unit_literals_are_parsed`,
`test_compound_units_resolve_and_convert`,
`test_compound_unit_literals_evaluate_to_si`,
`test_unknown_compound_unit_is_reported`,
`test_offset_unit_is_rejected_in_compound_unit`.

Eylem testleri: `test_action_call_executes_body`,
`test_action_call_binds_arguments`, `test_action_call_accepts_actor_parameter_and_defaults`,
`test_nested_action_calls_restore_the_caller_scope`,
`test_recursive_action_call_is_rejected`, `test_action_call_arguments_are_checked`.

Bölüm 4 ve 5 tablolarındaki diğer tanılamalar da aynı `parse → analyze →
compile` zinciriyle tekrarlanabilir.

## 11. İlişkili belgeler

- [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) — kapsam ve takvim
- [`docs/SCOPE_AUDIT.md`](SCOPE_AUDIT.md) — Must/Should kalemlerinin denetimi
- [`docs/VALIDATION.md`](VALIDATION.md) — ölçüm ve determinizm raporu
- [`docs/STAGES.md`](STAGES.md) — aşama aşama öğrenme yolu
