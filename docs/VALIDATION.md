# Aşama 5 — Doğrulama ve Ölçüm Raporu

Bu rapor, OSC2 → CARLA derleyicisinin makaledeki iddiaları ne ölçüde karşıladığını
ölçülebilir kanıtlarla gösterir. Üç soruya cevap arar:

1. **Doğru çalışıyor mu?** Senaryolar beklenen olayları üretiyor ve geometrik
   koşullar sağlanıyor mu?
2. **Tekrarlanabilir mi?** Aynı girdi, aynı trace'i üretiyor mu?
3. **Maliyeti ne?** Derleme ve tick gecikmesi, elle yazılmış bir CARLA
   kontrol grubuna göre ne kadar farklı?

Ölçümler 2026-10-26 tarihinde, tek makinede alınmıştır. Ham veriler
[`docs/measurements/`](measurements/) altındadır.

## 1. Ölçüm ortamı

| Bileşen | Değer |
| --- | --- |
| Python | 3.12 (venv) |
| CARLA | 0.9.16, `Town10HD_Opt` |
| Simülasyon adımı | 0.05 s (CARLA), 0.1 s (mock) |
| Spawn indeksi | 20 (sol şerit görüşüne göre sıralanmış listede) |
| Bağlantı | `127.0.0.1:2000`, synchronous mode |
| Trace tekrarı | 20 (mock ve CARLA), 20 derleme tekrarı (mock) |

CARLA ölçümü aynı sunucu sürecine art arda bağlanır; `close()` her koşudan sonra
aktörleri yok eder ve settings/weather değerlerini geri yükler.

## 2. Senaryo seti ve mock sonuçları

Beş senaryo, CARLA olmadan `MockAdapter` üzerinde çalıştırıldı. Her senaryo
20 kez tekrarlandı.

| ID | Senaryo | Durum | Tick | Süre | Olaylar | Trace hash (ilk 12) |
| --- | --- | --- | ---: | ---: | --- | --- |
| S1 | `scenarios/carla/cut_in.osc` | SUCCESS | 41 | 4.0 s | `CUT_IN` | `4c0cdd1fccd7` |
| S2 | `scenarios/dev/lane_change_speed.osc` | SUCCESS | 13 | 1.2 s | `LANE_CHANGED`, `DONE` | `a7f99db0c475` |
| S3 | `scenarios/dev/event_handshake.osc` | SUCCESS | 4 | 0.3 s | `PING`, `PONG`, `DONE` | `8ce2b96b79bf` |
| S4 | `scenarios/dev/placement_modes.osc` | SUCCESS | 3 | 0.2 s | `PLACED` | `4671bbc0b97b` |
| S5 | `scenarios/dev/environment_lights.osc` | SUCCESS | 13 | 1.2 s | `NIGHT_MODE` | `0de7509b017e` |

Her senaryoda beklenen olay kümesi birebir eşleşti; desteklenmeyen yapı
(`unsupported`) listesi boş kaldı. Bu, "sessizce yok sayma" politikasının da
çalıştığını gösterir: desteklenmeyen bir düğüm olsaydı derleme uyarısı ve
`FAILED` yaprak olarak görünürdü.

Senaryoların kapsadığı özellikler:

- **S1:** durative `drive`, `one_of`, `change_lane`, olay, fren, ışık.
- **S2:** şerit değişimi + `speed(at:)` modifier'ı.
- **S3:** iki paralel dal arasında `emit` / `wait @event` el sıkışması.
- **S4:** mutlak `x/y/z`, göreli `ahead_of` + `distance`, `behind` yerleşimi.
- **S5:** güneş açısı, otomatik/uzun far ve hız değişimi.

## 3. Determinizm

### Yöntem

Her tick'te aktörlerin `s`, şerit, hız, ışık ve `x/y/z` değerleri 6 ondalık
basamağa yuvarlanıp sıralı bir JSON yapısına yazılır. Tüm tick dizisinin
SHA-256 özeti **trace hash**'tir. Aynı senaryo için 20 koşunun hash'leri
karşılaştırılır.

### Sonuçlar

| Ortam | Senaryo | Koşu | Benzersiz hash | Sonuç |
| --- | --- | ---: | ---: | --- |
| Mock | 5 senaryo | 20 × 5 | 1 (her senaryo) | deterministik |
| CARLA | cut-in | 20 | 1 | deterministik |

CARLA hash'i:
`afaf910cd26b9c675f048d368ff177dce6a1132309df22031e836474a3f9c79b`

Bu sonuç, synchronous mode + sabit `fixed_delta_seconds` + aynı spawn noktası
birleşiminin aynı fizik adımlarını ürettiğini gösterir. Fizik motorunun
çekirdek determinizmi garanti edilmez; burada gözlenen determinizm aynı
makine, aynı sunucu ve aynı sürüm koşullarındadır.

### 2026-10-27 yeniden üretim notu

Ölçümler aynı makinede bağımsız olarak tekrarlandı; ham kanıt
[`docs/measurements/2026-10-27/`](measurements/2026-10-27/) altındadır.

| Ölçüm | 2026-10-26 | 2026-10-27 | Değerlendirme |
| --- | --- | --- | --- |
| Mock trace hash'leri (5 senaryo) | 5 sabit hash | birebir aynı | yeniden üretildi |
| Mock derleme süreleri | 2.63–75.19 ms | 2.61–90.25 ms | makine yüküne bağlı, değişir |
| CARLA başarı | 20/20 | 20/20 + 20/20 (iki oturum) | yeniden üretildi |
| CARLA geometri | 20/20 | 20/20 + 20/20 | yeniden üretildi |
| CARLA benzersiz hash | 1 | 1. oturum **2**, 2. oturum 1 | kısmen yeniden üretildi |

İlk CARLA oturumunda 20 koşunun 19'u `afaf910c...`, 1'i `8d185e5f...` hash'ini
üretti. İki trace arasındaki tek fark bir tick'teki `hero_speed` değeriydi:
`2.966754` yerine `2.96676` m/s (yaklaşık `6 × 10⁻⁶`). Tüm koşular `SUCCESS`,
`CUT_IN` ve geometri kontrolleri 20/20 geçti; KPI'lar raporlanan duyarlılıkta
aynı kaldı. İkinci oturumda 20/20 koşu aynı hash'i verdi.

**Sonuç:** Mock için bit düzeyinde trace determinizmi yeniden üretildi. CARLA
için davranış ve geometri determinizmi yeniden üretildi, ancak bit düzeyinde
trace hash determinizmi garanti değildir. Tezde bu iki iddia ayrılmalıdır:
"aynı davranış" desteklenir, "her zaman aynı hash" CARLA için desteklenmez.

## 4. Mock performansı

20 derleme tekrarının medyanı:

| ID | Parse (ms) | Analiz (ms) | BT derleme (ms) | Toplam (ms) | Tick p95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1 | 74.69 | 0.30 | 0.19 | 75.19 | 0.0191 |
| S2 | 58.63 | 0.35 | 0.14 | 59.06 | 0.0241 |
| S3 | 2.34 | 0.19 | 0.08 | 2.63 | 0.0296 |
| S4 | 29.36 | 0.34 | 0.11 | 29.77 | 0.0132 |
| S5 | 70.76 | 0.23 | 0.11 | 71.13 | 0.0126 |

**Yorum:** Süre baskın olarak parser'da. ANTLR'ın uyarlamalı tahmini (adaptive
prediction), fiziksel literal ve girinti kararlarında dosya içeriğine göre
belirgin biçimde değişiyor: aynı büyüklük mertebesindeki S3 2.34 ms'de
ayrışırken S1 74.69 ms sürüyor. Analiz ve BT üretimi toplamın %1'inden az.
Runtime tick gecikmesi 0.01–0.03 ms mertebesinde; mock için darboğaz değil.

Bu, raporlanması gereken bir **performans bulgusu**: derleme süresi senaryo
boyutundan çok, parser'ın belirsizlik çözümüne bağlı. İleride left-factor /
öncelik ayarı veya iki aşamalı lexer ile iyileştirilebilir; bu projede
doğruluk ve determinizm önceliklendirildi.

## 5. CARLA cut-in sonuçları (20 koşu)

| Metrik | Değer |
| --- | --- |
| Başarı | 20/20 |
| `CUT_IN` algılama | 20/20 |
| Geometri kontrolü | 20/20 |
| Benzersiz trace hash | 1 |
| Tick sayısı | 108 (tüm koşular) |
| Simülasyon süresi | 5.35 s |
| `CUT_IN` zamanı | 3.25 s (medyan, p95, min, max aynı) |
| Olay anı \|yanal\| sapma | 1.2978 m |
| Olay anı başlık farkı | 6.7218° |
| Olay anı `ahead_of` | −12.1548 m (hâlâ önde) |
| Başlangıç yanal sapması | −3.5 m (bir şerit sol) |
| Minimum mesafe | 11.938 m |
| Minimum TTC | 24.4897 s |
| Çarpışma | 0 |
| Tick gecikmesi (medyan) | 5.4528 ms |
| Tick gecikmesi (p95) | 5.4997 ms |

**Geometri kontrolü** iki koşul ister: `CUT_IN` anında |yanal sapma| < 2.2 m
(araç hedef şeritte) ve `ahead_of` negatif (NPC hâlâ hero'nun önünde). 20/20
koşuda sağlandı.

### Derleme süresi

| Aşama | Medyan | Not |
| --- | ---: | --- |
| Parse | 113.2 ms | ilk koşu 344.2 ms |
| Analiz | 0.40 ms | kararlı |
| BT derleme | 15.95 ms | ilk koşu 4032.9 ms |
| Toplam | 129.8 ms | ilk koşu 4377.5 ms |

İlk CARLA koşusundaki 4.03 s'lik BT derleme sıçraması, CARLA Python
istemcisinin ve blueprint kütüphanesinin ilk kullanımındaki tek seferlik
maliyettir; sonraki 19 koşuda BT derleme 15.3–26.0 ms aralığında. Raporlanan
"steady-state" değer bu nedenle 129.8 ms'dir; ortalama (217.3 ms) ilk koşu
tarafından yukarı çekilir.

## 6. Elle yazılmış CARLA baseline ile karşılaştırma

`tools/baseline_carla.py`, derleyiciyi kullanmayan bağımsız bir kontrol
grubudur: aynı harita ve spawn noktasında iki aracı doğrudan CARLA API'siyle
sürer, saf takip direksiyonu ve oransal hız kontrolü uygular, NPC'yi 2 s sonra
şerit değiştirir, hero'yu 3.2 s sonra frenletir. Beş koşu alınmıştır.

| Metrik | Derleyici (20 koşu) | Baseline (5 koşu) |
| --- | ---: | ---: |
| Başarı | 20/20 | 5/5 |
| `CUT_IN` zamanı | 3.25 s | 4.25 s |
| \|yanal\| sapma | 1.298 m | 1.701 m |
| Başlık farkı | 6.72° | 7.17° |
| `ahead_of` | −12.155 m | −11.478 m |
| Minimum mesafe | 11.938 m | 8.272 m |
| Minimum TTC | 24.49 s | 4.43 s |
| Çarpışma | 0 | 0 |
| Tick gecikmesi (medyan) | 5.453 ms | 5.249 ms |
| Tam döngü (medyan) | — | 5.375 ms |

**Yorum:**

- Derleyicinin tick maliyeti, baseline'ın tam döngüsüne (engine tick + kontrol
  hesabı) çok yakın: 5.453 ms'ye karşı 5.375 ms, yaklaşık **%1.4** fark. Ham
  engine tick'ine göre fark %3.9; bu, BT tick'lemesi ve ifade değerlendirmesinin
  maliyetidir ve 0.2 ms mertebesindedir.
- Derleyici cut-in'i daha erken (3.25 s) tamamlıyor ve olay anında daha küçük
  yanal/başlık sapması raporluyor. Bu bir "daha iyi sürüş" iddiası değildir:
  iki uygulamanın hız profilleri, şerit değişim tetikleyicisi ve tamamlanma
  ölçütü birebir aynı değil. Baseline, derleyicinin ürettiği davranışa karşı
  **ölçüm kontrolü**, algoritmik eşdeğer değildir.
- Minimum mesafe ve TTC farkı da aynı nedenden büyüktür: baseline hero'yu daha
  uzun süre sabit hızda tutar, derleyici olaydan sonra freni daha erken uygular.

## 7. Kapsam matrisi (makale Table 2)

Makale Table 2'deki işaretler PDF'ten güvenilir biçimde çıkarılamadı (ortamda
`pdftoppm` yok). Bunun yerine her satırı **çalışan kanıtla** eşleyen açık bir
matris kuruldu: [`docs/measurements/coverage.md`](measurements/coverage.md).

| Kategori | Desteklenen | Kısmi | Desteklenmeyen |
| --- | ---: | ---: | ---: |
| Action framework | 3 | 1 | 0 |
| Movement | 2 | 2 | 1 |
| Position & path | 2 | 2 | 3 |
| Environment | 1 | 0 | 3 |
| Modifiers | 5 | 2 | 1 |
| Coordinate systems | 2 | 1 | 1 |
| Scenario composition | 9 | 2 | 0 |
| **Toplam (43)** | **24** | **10** | **9** |

- Katı oran (yalnızca `supported`): **%56**
- Ağırlıklı oran (`supported` = 1, `partial` = 0.5): **%67**

Her satırda durum, kanıt dosyası/testi ve gerekçe vardır. `tools/coverage.py`
matrisi doğrular: geçersiz durum, var olmayan kanıt yolu, var olmayan test
fonksiyonu, yinelenen satır veya gerekçesiz `unsupported` satırı rapor eder.

**Desteklenmeyenlerin başlıcaları:** ivme kontrolü/modifier'ı, rota ve
trajectory takibi, zaman açığı (time gap), trafik ışıkları, hava/yol durumu,
fiziksel sürüş modu anahtarı. Bunlar sessizce yok sayılmaz; kullanılırsa
derleme uyarısı ve `FAILED` yaprak üretilir.

## 8. Test durumu

| Paket | Komut | Sonuç |
| --- | --- | --- |
| CARLA'sız | `pytest -q -m "not carla"` | 169 passed |
| CARLA | `pytest -q -m carla` | 3 passed |
| Toplam | `pytest -q` | 172 (3'ü CARLA marker'lı) |

Bu sayılar 27 Ekim 2026 grammar/stdlib geçişi, nitelikli eylem (qualified
action) yürütme düzeltmesi, eylem gövdesine modifier aktarımı ve kullanıcı
tanımlı modifier genişletmesinden sonradır; aşağıdaki Aşama 5 ölçümleri daha
erken bir sürümle alınmıştır ve ölçüm değerleri değişmemiştir.

Aşama 5'te eklenenler:

- 4 yeni senaryo (S2–S5) + golden AST dosyaları.
- `src/osc2c/validation.py`: trace hash, determinizm, derleme/tick ölçümü,
  KPI (minimum mesafe, TTC, çarpışma) ve Markdown özeti.
- `src/osc2c/coverage.py` + `tools/coverage.py`: 43 satırlık kanıtlı matris.
- `tools/bench.py`: `--mode mock|carla|all`, JSON/Markdown çıktısı.
- `tools/baseline_carla.py`: derleyicisiz kontrol grubu.
- `tests/test_validation.py`: 14 test — senaryo sonuçları, olaylar, geometri,
  determinizm, derleme aşamaları ve kapsam matrisi doğrulaması.

## 9. Yeniden üretme

```bash
cd C:\Users\canke\Desktop\osc2-carla
.venv\Scripts\activate

# Mock: 5 senaryo × 20 tekrar + 20 derleme tekrarı
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 \
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md

# CARLA: 20 cut-in koşusu (sunucu açık olmalı)
python tools/bench.py --mode carla --carla-repeat 20 \
  --json docs/measurements/carla.json --markdown docs/measurements/carla.md

# Kontrol grubu: derleyicisiz 5 koşu
python tools/baseline_carla.py --repeat 5 \
  --json docs/measurements/baseline_carla.json

# Kapsam matrisi
python tools/coverage.py --json docs/measurements/coverage.json \
  --markdown docs/measurements/coverage.md
```

CARLA sunucusu yoksa yalnızca mock ve kapsam komutları çalışır; CARLA
komutları bağlantı hatasıyla durur. Varsayılan test paketi CARLA gerektirmez.

## 10. Sınırlılıklar ve geçerlilik tehditleri

1. **Tek harita, tek spawn noktası.** Tüm CARLA ölçümleri `Town10HD_Opt`
   üzerinde 20 numaralı spawn noktasında alındı. Başka harita/kavşak/şerit
   düzenlerinde davranış doğrulanmadı.
2. **Tek makine, aynı CARLA süreci.** Determinizm aynı sürüm ve donanımda
   gözlendi; farklı fizik adımları, sunucu sürümleri veya eşzamanlı yük
   altında tekrar test edilmedi.
3. **Baseline basitleştirilmiş.** Elle yazılan kontrol grubu, derleyicinin
   ürettiği davranışın birebir eşdeğeri değil; amaç mutlak performans değil,
   aynı işi yapan iki yaklaşımın maliyet mertebesini karşılaştırmak.
4. **İlk koşu ısınma etkisi.** CARLA'da ilk derleme 4.03 s; ortalamalar bu
   nedenle yanıltıcı. Rapor medyan ve steady-state değerleri kullanır.
5. **Parser maliyeti içerik bağımlı.** Mock derleme süreleri 2.6–75.2 ms
   arasında değişiyor; bu, ANTLR uyarlamalı tahmininin fiziksel literal ve
   girinti kararlarındaki davranışından kaynaklanıyor. Derleme süresi için
   tek bir sabit değer vermek yanlış olur.
6. **ASAM standart dosyaları yok.** `types.osc` / `domain.osc` lisans nedeniyle
   repoda değil; yerleşik alt küme kullanılıyor. Bu, kapsam matrisindeki
   `unsupported` satırlarının bir kısmını açıklar.
7. **Kapsam matrisi makale işaretlerinin birebir kopyası değil.** PDF'ten
   çıkarılamayan işaretler yerine çalışan kanıt ve gerekçe kaydedildi; bu,
   karşılaştırmayı daha denetlenebilir ama makale tablosuyla birebir değil.
8. **KPI'lar tek cut-in senaryosuna özgü.** Minimum mesafe/TTC eşikleri başka
   senaryolara genellenemez; harness her senaryo için yeniden tanımlanmalı.

## 11. Aşama 5'in cevapladığı sorular

- **"Deterministik" ne demek?** Aynı senaryo, aynı adaptör ayarları ve aynı
  simülasyon adımıyla çalıştırıldığında tick-by-tick aktör durumunun aynı
  SHA-256 özetini vermesi. Fizik motorunun mutlak determinizmi iddia edilmez.
- **Hangi metrik neyi ölçer?** Derleme süresi dil ön yüzünün (parser ağırlıklı)
  maliyetini; tick gecikmesi runtime + adaptörün gerçek zamanlı maliyetini;
  trace hash tekrarlanabilirliği; KPI'lar senaryo davranışının doğruluğunu.
- **Sessizce yok sayma neyi bozar?** Senaryo "başarılı" görünür ama test
  edilmek istenen manevra hiç uygulanmamış olur; bu, yanlış güven üretir.
  Bu nedenle desteklenmeyen düğüm uyarı + `FAILED` yaprak olarak yüzeye çıkar.
