# 2026-10-27 — Bağımsız yeniden üretim oturumu

Bu klasör, 2026-10-26 tarihli `docs/VALIDATION.md` raporundaki mock ve CARLA
ölçümlerinin aynı makinede yeniden üretilmesinin kanıtlarını saklar. Amaç yeni
bir sonuç üretmek değil, eski sonuçların hâlâ geçerli olup olmadığını
denetlemektir.

## Klasördeki dosyalar

| Dosya | İçerik |
| --- | --- |
| `mock.json`, `mock.md` | 2026-10-27 mock koşusu (5 senaryo × 20 tekrar, 20 derleme tekrarı) |
| `coverage.json`, `coverage.md` | 2026-10-27 kapsam matrisi doğrulaması |
| `carla.json`, `carla.md` | CARLA **ikinci** oturumu (B); 20/20 aynı hash |
| `console.log` | İki CARLA oturumunun (A ve B) tam konsol kaydı |

> Önemli: `carla.json` ve `carla.md` ikinci oturumun (B) çıktısıdır. İlk
> oturumun (A) 2 benzersiz hash ürettiği kanıt yalnızca `console.log` içinde
> durur. Bu nedenle ayrıntılı sayılar aşağıda ve `console.log` satırlarında
> kayıtlıdır.

## 1. Mock koşusu

Komut:

```powershell
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 `
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md
```

Sonuç: 5/5 senaryo `SUCCESS`, beklenen olay kümeleri birebir eşleşti,
`unsupported` listeleri boş, her senaryoda `unique_hashes = 1`.

Trace hash'leri 2026-10-26 raporuyla **birebir aynı**:

| ID | Trace hash (ilk 12) | Rapordaki değer |
| --- | --- | --- |
| S1 | `4c0cdd1fccd7` | aynı |
| S2 | `a7f99db0c475` | aynı |
| S3 | `8ce2b96b79bf` | aynı |
| S4 | `4671bbc0b97b` | aynı |
| S5 | `0de7509b017e` | aynı |

Zamanlama değerleri birebir aynı değil; bu beklenen bir durumdur:

| ID | Derleme medyanı (26 Ekim) | Derleme medyanı (27 Ekim) |
| --- | ---: | ---: |
| S1 | 75.19 ms | 90.25 ms |
| S2 | 59.06 ms | 56.88 ms |
| S3 | 2.63 ms | 2.61 ms |
| S4 | 29.77 ms | 29.33 ms |
| S5 | 71.13 ms | 67.61 ms |

Yorum: Trace hash'i dil ve yürütme semantiğinin determinizmini ölçer; duvar
saati süreleri makine yüküne ve parser'ın uyarlamalı tahminine bağlıdır.
Dolayısıyla "deterministik" iddiası yalnızca trace için geçerlidir, süreler
için değildir.

## 2. CARLA oturumu A — 20 koşu, 2 benzersiz hash

Sonuç: 20/20 `SUCCESS`, 20/20 `CUT_IN`, 20/20 geometri kontrolü, 0 çarpışma.

| Alan | Değer |
| --- | --- |
| Benzersiz hash | **2** |
| Baskın hash | `afaf910cd26b9c675f048d368ff177dce6a1132309df22031e836474a3f9c79b` (19 koşu) |
| Aykırı hash | `8d185e5f4e22e6644f22b084c4db1f7f09f86995401145dedcb52affb7da16da` (1 koşu) |
| `CUT_IN` zamanı | 3.25 s (tüm koşular) |
| Olay anı \|yanal\| sapma | 1.2978 m |
| Olay anı başlık farkı | 6.7218° |
| Olay anı `ahead_of` | −12.1548 m |
| Minimum mesafe | 11.938 m |
| Minimum TTC | 24.4897 s |
| Tick sayısı | 108 |

İki hash arasındaki tek fark, aykırı koşuda bir tick'te kaydedilen
`hero_speed` değeridir:

- 19 koşu: `2.966754` m/s
- 1 koşu: `2.96676` m/s
- Fark: yaklaşık `6 × 10⁻⁶` m/s

Bu fark 6 ondalık basamağa yuvarlanmış trace'e girdiği için hash'i
değiştirmiştir. KPI'lar raporlanan duyarlılıkta (4 ondalık) aynı kaldı ve tüm
koşular başarılı oldu. Yani bu bir davranış/geometri hatası değil, kayan nokta
ve fizik motoru gürültüsüdür.

## 3. CARLA oturumu B — 20 koşu, 1 benzersiz hash

Aynı komut ikinci kez çalıştırıldı:

```powershell
python tools/bench.py --mode carla --carla-repeat 20 `
  --json docs/measurements/carla.json --markdown docs/measurements/carla.md
```

Sonuç: 20/20 `SUCCESS`, 20/20 `CUT_IN`, 20/20 geometri kontrolü, 0 çarpışma,
**1 benzersiz hash**: `afaf910cd26b...` (oturum A'nın baskın hash'i ile aynı).
Tüm KPI'lar oturum A ile aynı.

## 4. Sonuç

- Mock tarafında **birebir trace determinizmi** yeniden üretildi.
- CARLA tarafında **davranışsal ve geometrik determinizm** yeniden üretildi:
  20/20 başarı, aynı olay zamanı, aynı KPI'lar.
- CARLA'da **bit düzeyinde trace hash determinizmi garanti değildir**: iki
  oturumdan birinde 20 koşunun 1'i 6e-6 m/s'lik bir hız farkıyla ayrı hash
  üretti. Bu, `docs/VALIDATION.md` §3'teki "fizik motorunun çekirdek
  determinizmi garanti edilmez" uyarısıyla tutarlıdır.
- Bu nedenle tezde iki ifade ayrılmalıdır:
  1. "Aynı senaryo aynı davranışı ve geometriyi üretir" — 20/20 destekleniyor.
  2. "Aynı senaryo her zaman aynı trace hash'ini üretir" — CARLA için
     desteklenmiyor; mock için destekleniyor.
