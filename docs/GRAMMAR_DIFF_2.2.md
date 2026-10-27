# ASAM OpenSCENARIO DSL 2.2.0 EBNF ↔ Proje Grammar Farkı — 27 Ekim 2026

Bu belge, ASAM'ın yayımladığı 2.2.0 paketindeki `grammar.ebnf` ile projenin
kullandığı vendored grammar'ı kural kural karşılaştırır. Amaç "tam uyum"
iddiası değil; her farkı sınıflandırmak, gerçek boşlukları kapalı bir listeye
indirmek ve kalan sapmaları testle izlenebilir kılmaktır. Önceki sürüm
[`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) dil yapılarının uçtan uca kapsamını
anlatır; bu belge ise yalnızca **grammar düzeyindeki** farklara odaklanır.

## 1. Kaynaklar

| Dosya | Konum | Boyut |
|---|---|---|
| 2.2.0 EBNF grammar | `external/asam/grammar.ebnf` | 459 satır, 18.615 B |
| 2.2.0 tip kütüphanesi | `external/asam/types.osc` | 114 bildirim (`namespace stdtypes`) |
| 2.2.0 domain kütüphanesi | `external/asam/domain.osc` | 186 bildirim (`namespace std`, `types.osc` import'u) |
| 2.2.0 giriş noktası | `external/asam/standard.osc` | 2 import, 0 bildirim |
| Proje grammar'ı | [`grammar/openscenario2.g4`](../grammar/openscenario2.g4) | 333 satır (MPL-2.0 bildirimi korunur) |

ASAM dosyalarının başlığı dağıtım iznini açıkça verir:

> In alteration to the regular license terms, ASAM allows unrestricted
> distribution of this standard.

Buna karşın `external/` hâlâ `.gitignore` içindedir; dosyalar repoya
alınmadı, yalnızca yerel doğrulama için kullanıldı. Bu politika kararı
bölüm 8'de ele alınır.

## 2. Yöntem

Kural adları mekanik olarak çıkarıldı: EBNF için `^ad ::=`, ANTLR için
`^ad:` başlıkları; ardından adlar küçük harfe çevrilip `-` → `_`
normalleştirildi. ANTLR'daki `#etiket` alternatifleri ayrı kural sayılmaz.
Sonuç:

```text
EBNF kuralı            : 165
Proje parser kuralı    : 154
Proje lexer kuralı     : 16   (toplam 170)
```

Ad düzeyinde 16 EBNF-only ve 5 proje-only kural var. Bunların tamamı
bölüm 3'te tek tek sınıflandırıldı; ad farkı tek başına davranış farkı
demek olmadığı için asıl kanıt bölüm 5'teki gerçek kütüphane koşusudur.

## 3. Ad düzeyindeki farkların sınıflandırması

### 3.1 Yalnız EBNF'te olan 16 kural

| EBNF kuralı | Projede karşılığı | Sınıf |
|---|---|---|
| `cast-exp`, `type-test-exp`, `element-access`, `function-application` | `postfix_exp` içinde `#cast_exp_pe`, `#type_test_exp_pe`, `#element_access_pe`, `#function_application_pe` ([g4:271-276](../grammar/openscenario2.g4#L271)) | Aynı dil, farklı örgütlenme (ANTLR etiketi) |
| `sum` | `sum_exp` ([g4:262](../grammar/openscenario2.g4#L262)) | Yeniden adlandırma |
| `non-structural-type-declarator`, `structural-type-declarator` | `non_aggregate_type_declarator` + `declared_type_name` ([g4:72-73](../grammar/openscenario2.g4#L72)) | Sözdizimsel ayrım anlamsal kata taşındı; üst küme |
| `physical-type-name` | `declared_type_name` → `qualified_identifier` ([g4:73](../grammar/openscenario2.g4#L73)) | Yeniden adlandırma |
| `digit`, `hex-digit` | `fragment DIGIT`, `fragment HEX_DIGIT` ([g4:309-310](../grammar/openscenario2.g4#L309)) | Lexer fragment'ı |
| `int-literal` | `INT_LITERAL` ([g4:308](../grammar/openscenario2.g4#L308)) | Lexer kuralı |
| `shortstring`, `longstring` | `SHORTSTRING`, `LONGSTRING` ([g4:296-297](../grammar/openscenario2.g4#L296)) | Lexer kuralı |
| `shortstring-elem`, `longstring-elem`, `string-escape-seq` | Lexer regex'i içinde satır içi ([g4:296-297](../grammar/openscenario2.g4#L296)) | Kaçış dizileri serbest bırakıldı (bölüm 4) |

### 3.2 Yalnız projede olan 5 kural

| Proje kuralı | EBNF'teki durum | Sınıf |
|---|---|---|
| `declared_type_name` | `physical-type-name` + yapısal adların tümü `qualified-identifier` | Birleştirme |
| `sum_exp` | `sum` | Yeniden adlandırma |
| `unit_expression`, `unit_term` ([g4:321-322](../grammar/openscenario2.g4#L321)) | Eşdeğeri yok; `physical-literal` tek `unit-name` alır ([EBNF:457](../external/asam/grammar.ebnf#L457)) | **Kasıtlı üst küme** (bileşik birimler) |
| `use_statement` ([g4:43](../grammar/openscenario2.g4#L43)) | 2.2'de kaldırıldı ([EBNF:21](../external/asam/grammar.ebnf#L21)) | **Sürüm farkı** (2.1 hedefi) |

Ad düzeyindeki incelemenin sonucu: 21 ad farkından yalnızca **dördü**
davranışsal — bileşik birimler, top-level `use`, serbest string kaçışları ve
`.as()`/`.is()` hedefinde tüm tip bildirimlerinin kabul edilmesi. Geri kalanı
yeniden adlandırma, satır içine alma veya lexer ayrıntısıdır.

## 4. Sürüm farkı: 2.1 hedefi ↔ 2.2.0 paketi

Proje OpenSCENARIO **2.1**'i hedefliyor; elde edilebilen resmî paket
**2.2.0**. Bu ikisi arasında bilinen ve projeyi etkileyen farklar:

1. **Top-level `use` kaldırıldı.** 2.2'de `prelude-statement ::= import-statement`
   ([EBNF:21](../external/asam/grammar.ebnf#L21)); `use` yalnızca
   `namespace X use Y` içinde yaşıyor ([EBNF:36](../external/asam/grammar.ebnf#L36)).
   Proje 2.1 uyumu için `prelude_statement: import_statement | use_statement`
   biçimini koruyor ([g4:39-43](../grammar/openscenario2.g4#L39)).
2. **Ad alanı adları değişti.** Paket `namespace stdtypes` ve
   `namespace std` kullanıyor (`types.osc:17`, `domain.osc:19`); 2.1
   belgelerinde kök adlar `std::stdtypes` / `std::standard` olarak geçer.
   Projenin yerleşik alt kümesi ve testleri 2.2 adlarını kullanır
   ([stdlib.py](../src/osc2c/semantics/stdlib.py)).
3. **Enum değerleri işaretsiz.** 2.2:
   `enum-member-value ::= uint-literal | hex-uint-literal | enum-value-reference`
   ([EBNF:102](../external/asam/grammar.ebnf#L102)). Projede
   `integer_literal` de kabul edilir ([g4:104](../grammar/openscenario2.g4#L104)),
   yani negatif değerlerde üst küme.
4. **Noktalı davranış adları gerçek kütüphanede yoğun.** `domain.osc`
   içinde 100'den fazla `action <aktör>.<ad>` bildirimi var
   (ör. `action vehicle.drive`, `domain.osc:1246`). Grammar bunu destekliyor;
   anlamsal katmanda kalan boşluk bölüm 6'dadır.

## 5. Bu geçişte kapatılan üç gerçek boşluk

Gerçek 2.2.0 kütüphanesi ayrıştırılırken üç sözdizimi boşluğu ortaya çıktı
ve kapatıldı. Üçü de aynı hatayla tetiklendi: `domain.osc` parser'da
durduğu anda 186 bildirimin tamamı kayboluyordu.

| # | 2.2 kuralı | Önce | Şimdi | Kanıt |
|---|---|---|---|---|
| 1 | `enum-member-value ::= uint-literal \| hex-uint-literal \| enum-value-reference` ([EBNF:99-104](../external/asam/grammar.ebnf#L99)) | `domain.osc:430: mismatched input 'heavy_truck' expecting INTEGER_LITERAL` (enum takma adı `truck = heavy_truck`) | `enum_value_reference` kuralı ([g4:106](../grammar/openscenario2.g4#L106)); AST `EnumValueRef` ([ast.py:118](../src/osc2c/frontend/ast.py#L118)); iki geçişli çözüm + `E0103` ([builder.py:518](../src/osc2c/semantics/builder.py#L518)) | `test_enum_member_value_may_reference_another_member`, `test_enum_member_reference_copies_the_value`, `test_unknown_enum_member_reference_is_reported` |
| 2 | `range-type-declarator ::= 'range' 'of' numeric-type-declarator` ([EBNF:112](../external/asam/grammar.ebnf#L112)) | `list of range of int` ayrıştırılamıyordu | `aggregate_type_declarator`, `range_type_declarator`, `numeric_type_declarator` ([g4:75-80](../grammar/openscenario2.g4#L75)); AST `RangeType` ([ast.py:234](../src/osc2c/frontend/ast.py#L234)); `RangeTypeInfo` ([builder.py:1576](../src/osc2c/semantics/builder.py#L1576)) | `test_range_type_declarators_parse`, `test_range_declarator_resolves_to_a_range_type` |
| 3 | `primitive-type-extension ::= 'extend' primitive-type ':' NEWLINE INDENT method-declaration+ DEDENT` ([EBNF:162-172](../external/asam/grammar.ebnf#L162)) | `extend float:` ayrıştırılamıyordu | `type_extension` üç alternatifli ([g4:134-136](../grammar/openscenario2.g4#L134)); AST `PrimitiveExtensionDecl` ([ast.py:381](../src/osc2c/frontend/ast.py#L381)); yöntemler kaydedilir, çalıştırılmadıkları için `W0106` ([builder.py:843](../src/osc2c/semantics/builder.py#L843)) | `test_primitive_type_extension_parses`, `test_primitive_type_extension_is_reported_as_unexecuted` |

Ek olarak kütüphanenin yüklenmesini engelleyen iki anlamsal hata
düzeltildi (ayrıntı ve tanılama kodları
[`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) §8'de):

- **Alan/tip gölgeleme:** alan adları tipleri gölgelediğinde
  `E0202 '<x>' is a parameter, not type` üretiliyordu; tür-farkındalı
  sözcüksel arama eklendi.
- **Niteliksiz enum üyesi belirsizliği:** `keep(default it == other)`
  `E0404` veriyordu; beklenen tipe göre çözüm (`_infer_with_hint`) eklendi.
- **`actor` bağlamı:** action gövdelerinde `keep(default it == actor)`
  `E0402` veriyordu; action gövdesinde `actor` opak kabul ediliyor.
- **Modifier/tip adı çakışması:** `struct lane` ile `modifier lane` aynı
  adı paylaşınca `E0101` çıkıyordu; modifier'lar ayrı sözlükte tutuluyor
  ([scope.py](../src/osc2c/semantics/scope.py)).
- **Yerleşik + gerçek kütüphane çakışması:** ikisi birlikte kurulunca tüm
  semboller `E0101` veriyordu; gerçek kütüphane algılanınca yerleşik alt
  küme kurulmuyor ve aktörlere örtük `traffic_participant` tabanı
  eklenmiyor ([builder.py](../src/osc2c/semantics/builder.py)).

## 6. Noktalı davranış adlarının hedef tipe bağlanması

Grammar `<aktör>.<davranış>` biçimini kabul ediyor ve `domain.osc` bunu
48 bildirimde kullanıyor (`action vehicle.drive`, `action environment.air` vb.).
Önceki durumda anlamsal katman bu bildirimleri `std` ad alanında tek parça
ad olarak saklıyor, `vehicle.methods` boş kalıyor ve tüm çağrılar
`W0105 unknown behavior or method` alıyordu:

```text
hero.drive()   -> W0105
hero.assign_position() -> W0105
```

Bu geçişte `_resolve_signatures` sonuna `_attach_qualified_actions` eklendi
([builder.py:904](../src/osc2c/semantics/builder.py#L904)): `action A.b`
bildirimi, aynı ad alanındaki `A` aktörünün `methods` tablosuna `b` adıyla
bağlanıyor. Kalıtım zaten `_lookup_member` üzerinden yürüdüğü için
`vehicle` üzerinden `movable_object.change_speed` gibi taban davranışlar da
görünür. Doğrulanan davranış:

```text
hero.drive()                        -> tanılama yok
hero.assign_position()              -> tanılama yok
hero.change_speed(target: 5)        -> E0401 argument 'target' expects speed, got int
hero.change_speed(target_speed: 5 mps) -> E0406 no argument named 'target_speed'
hero.fly_away()                     -> W0105 (doğru: tanımsız)
```

**Bilinçli sınır:** 2.2 kütüphanesinde bir eylemin parametresinin zorunlu mu
isteğe bağlı mı olduğu yalnızca yorum satırında yazılıdır (`# Mandatory`,
`# Optional`); lexer yorumları attığı için bu bilgi makine tarafından
okunamaz. Bu nedenle kütüphaneden bağlanan eylemlerde ve standart
modifier'larda eksik argüman hata sayılmıyor, sağlanan argümanların adı ve
tipi denetleniyor. Kullanıcının kendi `action` bildirimlerinde mevcut katı
denetim (`E0405`) korunuyor. Gevşetme yalnızca `std`/`stdtypes` ad
alanlarına uygulanıyor ([builder.py:185](../src/osc2c/semantics/builder.py#L185)).

### 6.1 Backend'de yürütme

Bağlama artık yalnızca anlamsal değil, yürütülebilir de. Backend sırası:

1. Hedef üzerinde çözülen yöntem bir `action` bildirimiyse ve bildirimin
   (veya tabanının) `do`/`on` gövdesi varsa, gövde davranış ağacına
   derleniyor; parametreler, yerel `var`'lar ve `it` çağrı anında
   bağlanıyor ([compiler.py:307](../src/osc2c/backend/compiler.py#L307)).
   `it`, eylemi alan aktörü gösterir; anlamsal katman da eylem
   gövdelerinde `it`'i bu aktör olarak tipliyor
   ([builder.py:1187](../src/osc2c/semantics/builder.py#L1187)).
2. Gövdesi olmayan kütüphane eylemleri ada göre simülatör kayıt defterine
   düşüyor. `drive`, `walk`, `change_speed`, `assign_position`,
   `change_lane`, `set_lights`, `assign_celestial_position` yanında bu
   geçişte `move`, `assign_speed`, `keep_speed` ve `remain_stationary`
   eklendi ([method_registry.py:122](../src/osc2c/backend/method_registry.py#L122)).
3. Eşlemesi olmayan eylem (`follow_trajectory`, `connect_trailer`, ...)
   sessizce yutulmuyor: derleme uyarısı ve `FAILURE` yaprak üretiliyor.
4. Gövdesi olan eyleme uygulanan standart `with:` modifier'ları çağrı
   anında değerlendirilip eylem gövdesi boyunca ortam modifier'ı olarak
   tutuluyor. Gövdedeki `it` alıcılı kayıt defteri davranışları
   (`drive`, `assign_position`, ...) bu değerleri miras alıyor; iç `with:`
   aynı adı ezerse iç değer kazanıyor, farklı aktöre yapılan çağrı
   etkilenmiyor ([compiler.py:373](../src/osc2c/backend/compiler.py#L373),
   [behaviors.py:88](../src/osc2c/backend/behaviors.py#L88),
   [method_registry.py:78](../src/osc2c/backend/method_registry.py#L78)).
5. Kullanıcı tanımlı modifier'lar derleme zamanında düzleştiriliyor:
   gövdedeki standart uygulamalar doğrudan davranışlara, nitelikli eylem
   gövdelerine ve `at: start` yükseltmesine aktarılıyor. Kaynak sırası
   korunuyor (son uygulama kazanıyor), döngü ve desteklenmeyen gövde
   üyeleri uyarıyla raporlanıyor
   ([modifiers.py](../src/osc2c/backend/modifiers.py)). Eylem içi `until`
   ifadeleri çalışıyor.

Gözlenen sonuçlar (MockAdapter, 27 Ekim 2026):

```text
action timer.hold + t.hold(span: 200 ms)          -> SUCCESS, 0.2 s
action cruiser.cruise: it.drive() with speed(5 mps) -> SUCCESS, hız 5 mps
c.cruise() with: speed(5 mps) (gövde: it.drive())   -> SUCCESS, hız 5 mps
c.cruise() with: speed(5 mps), iç speed(3 mps)      -> SUCCESS, hız 3 mps
c.escort(n) with: speed(5 mps) (it + n sürüyor)     -> c 5 mps, n 0 mps
c.place() with: position(x: 10 m)                   -> SUCCESS, x 10 m
hero.drive() with: speed(10 mps) until elapsed(500 ms) -> SUCCESS, 5 m hız 10 mps
hero.assign_speed(speed: 5 mps)                   -> SUCCESS, hız 5 mps
hero.move() with: speed(4 mps) until elapsed(300 ms)   -> SUCCESS, 1.2 m hız 4 mps
hero.drive() with: fast() (fast -> speed(10 mps))  -> SUCCESS, hız 10 mps
c.boost() with: fast() (gövde: it.drive())          -> SUCCESS, hız 10 mps
hero.assign_position() with: start_fast() (at: start) -> SUCCESS, önceden uygulanır, hız 5 mps
a() where a -> b -> a                              -> döngü uyarısı, çalışma sürer
hero.follow_trajectory()                          -> uyarı + FAILURE
```

`_action_stack` nitelikli eylemlerde de kullanıldığı için öz yineleme
(`action looper.loop: it.loop()`) derleme anında `CompilationError` veriyor.

## 7. Doğrulama

Gerçek kütüphane, import zinciri çözülerek yüklendiğinde (CLI'ın
`_load_unit` davranışı) sembol tabloları:

```text
stdtypes : 112 sembol
std      : 154 sembol
tanılama : 0
```

CLI çıktıları:

```text
> osc2c check external\asam\standard.osc
external\asam\standard.osc: ok                      (exit 0)

> osc2c check scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc
asam_stdlib.osc:17:8: warning[W0102]: unknown event 'DONE'; external domain definition not loaded
                                                    (exit 0)

> osc2c bt scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc
  -> ActionLeaf hero.drive + ActionLeaf hero.assign_speed + EmitLeaf emit DONE
```

`scenarios/asam/asam_stdlib.osc` gerçek kütüphaneye karşı şunları çalıştırır:
`vehicle` kalıtımı, `hero.drive() with: speed(5 mps)` ve
`hero.assign_speed(speed: 0 mps)` üzerinden noktalı eylem çözümü ve
yürütme, `range of length`, `list of speed`, `list of range of int`, tipe
göre enum çözümü (`vehicle_category = car`) ve `it.rear_overhang` üzerinden
miras alan okuma. Tek uyarı, senaryoda tanımlanmamış `DONE` olayıdır; hata
değildir.

Test durumu (27 Ekim 2026):

```text
pytest -q -m "not carla"  ->  169 passed, 3 deselected
test_backend.py           ->   59 passed
test_semantics.py         ->   64 passed
test_frontend_ast.py      ->   27 passed
compileall + pip check    ->  temiz
```

Gerçek kütüphaneye bağlı testler `external/asam/standard.osc` yoksa
`skipif` ile atlanır; depo `external/` olmadan da yeşil kalır.

## 8. Karar bekleyen konu: `external/asam/` repoya alınsın mı?

ASAM başlığı sınırsız dağıtıma izin veriyor; ancak dosyalar şu anda
`.gitignore` içinde. Üç seçenek:

1. **Repoda tut (önerilen):** tekrarlanabilirlik artar, `skipif` testleri
   her klonda çalışır; `NOTICE` içine ASAM atfı ve izin metni eklenir.
2. **Script ile indir:** repoda yalnızca URL + SHA-256 kalır; CI ağa bağımlı
   olur.
3. **Yerel kalır:** mevcut durum; gerçek kütüphane testleri başka makinede
   atlanır.

Karar verilene kadar bölüm 7'deki sonuçlar yalnızca bu makinede tekrar
üretilebilir.

## 9. Yeniden üretim

```bash
cd C:\Users\canke\Desktop\osc2-carla
.venv\Scripts\python.exe -m pytest -q -m "not carla"
.venv\Scripts\osc2c.exe check external\asam\standard.osc
.venv\Scripts\osc2c.exe check scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc

# Kural envanterini yeniden çıkar (bölüm 2)
.venv\Scripts\python.exe - <<'PY'
import re
from pathlib import Path
ebnf = Path("external/asam/grammar.ebnf").read_text(encoding="utf-8")
g4 = Path("grammar/openscenario2.g4").read_text(encoding="utf-8")
g4 = re.sub(r"//.*", "", g4)
rules = re.findall(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\n?\s*:", g4, re.M)
print("EBNF:", len(re.findall(r"^([A-Za-z][A-Za-z0-9-]*)\s*::=", ebnf, re.M)),
      "| parser:", len([r for r in rules if not r.isupper()]),
      "| lexer:", len([r for r in rules if r.isupper()]))
PY
```

## 10. İlgili belgeler

- [`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) — dil yapılarının uçtan uca kapsamı
- [`STAGES.md`](STAGES.md) — aşama aşama öğrenme yolu
- [`SCOPE_AUDIT.md`](SCOPE_AUDIT.md) — Must/Should kalemlerinin denetimi
- [`VALIDATION.md`](VALIDATION.md) — ölçüm ve determinizm raporu
