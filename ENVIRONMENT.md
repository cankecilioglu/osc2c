# Ortam Kurulumu — 26 Ekim 2026

## Proje kökü

```text
C:\Users\canke\Desktop\osc2-carla
```

## Makine

- Windows 11 Pro (build 26300)
- AMD Radeon RX 7700 XT (12 GB), 32 GB RAM, ~156 GB boş disk
- AMD sürücü: 32.0.32015.7029 (18.10.2026)

## Kurulu bileşenler

| Bileşen | Sürüm | Konum |
|---|---|---|
| Python (proje) | 3.12.15 (uv standalone) | `C:\Users\canke\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe` |
| Python (eski) | 3.11.9 | `C:\Users\canke\AppData\Local\Programs\Python\Python311\python.exe` |
| Python (sistem) | 3.15 | `C:\Users\canke\AppData\Local\Python\pythoncore-3.15-64\python.exe` |
| Proje venv'i | 3.12.15 | `.venv\` (eski venv yedeği: `.venv311.bak\`) |
| JDK (Temurin) | 17.0.20.1 | `C:\Users\canke\tools\jdk17\jdk-17.0.20.1+1` |
| JDK (Microsoft, yedek) | 21.0.13 | `C:\Program Files\Microsoft\jdk-21.0.13.21-hotspot` |
| ANTLR aracı | 4.13.2 | `tools\antlr-4.13.2-complete.jar` |
| CARLA | 0.9.16 | `external\CARLA_0.9.16` |

Python bağımlılıkları `requirements.txt` ve `pyproject.toml` içinde sabitlendi.

## Python ortamı

```bash
cd C:\Users\canke\Desktop\osc2-carla
.venv\Scripts\activate
pytest -q
osc2c ast scenarios/dev/smoke4.osc
```

Windows'ta `python` komutu Store alias'ına gidebilir; venv içindeki `.venv\Scripts\python.exe` kullanılmalı.

### Python 3.12 neden uv ile kuruldu

CARLA 0.9.16 yalnızca `cp312` wheel yayınlıyor; proje 3.11'de kalamazdı. Windows Python 3.12 kurulum paketi yönetici izni (UAC) istediği için sessiz kurulum takıldı. `uv` ile yönetici izni gerektirmeyen standalone CPython 3.12 kuruldu:

```powershell
.venv\Scripts\python.exe -m pip install uv
.venv\Scripts\python.exe -m uv python install 3.12
.venv\Scripts\python.exe -m uv python find 3.12
```

Sonra venv yeniden oluşturuldu:

```powershell
mv .venv .venv311.bak
& "C:\Users\canke\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m pip install external\CARLA_0.9.16\PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl
```

## ANTLR grammar üretimi

```bash
python scripts/generate_parser.py
```

`java` PATH'te yoksa `JAVA_HOME` ayarlanır:

```powershell
$env:JAVA_HOME = "C:\Users\canke\tools\jdk17\jdk-17.0.20.1+1"
.venv\Scripts\python.exe scripts\generate_parser.py
```

Git Bash ile aynı komut:

```bash
JAVA_HOME="C:/Users/canke/tools/jdk17/jdk-17.0.20.1+1" .venv/Scripts/python.exe scripts/generate_parser.py
```

## Frontend spike sonucu

- py-osc2 0.1.0 grammar'ı OSC 2.0 seviyesindeydi; top-level `use` ve boşluklu fiziksel birimler desteklenmiyordu.
- Grammar MPL-2.0 temel alınarak genişletildi:
  - `use std.stdtypes` için `use_statement`
  - `35 kph` için `physical_literal` parser kuralı
  - `enum_member_value` → `integer_literal` (lexer `UINT_LITERAL`/`HEX_UINT_LITERAL` hiç üretmiyordu)
  - `unit_expression` / `unit_term` ile bileşik birimler (`m/s`, `km/h`, `m/s^2`, `m/s^-2`)
- ANTLR 4.13.2 ile yeniden üretildi.
- Paper tarzı iç içe `serial/parallel`, `emit`, `wait elapsed`, birimli ifadeler **0 hatayla** parse ediliyor.
- py-osc2 paketi, runtime 4.7.1 bağımlılığı nedeniyle kaldırıldı; grammar projeye vendored edildi (MPL-2.0 `NOTICE` ile).

## CARLA

- Paket: `C:\Users\canke\Downloads\CARLA_0.9.16.zip` (7,8 GB)
- Hedef: `external\CARLA_0.9.16` (git tarafından yok sayılır)
- Çıkarma:

```bash
C:\Windows\System32\tar.exe -xf C:\Users\canke\Downloads\CARLA_0.9.16.zip ^
  -C C:\Users\canke\Desktop\osc2-carla\external\CARLA_0.9.16
```

- Python wheel'i: `PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl` (venv'e kuruldu)
- Sunucu başlatma (görünür pencere):

```bash
external\CARLA_0.9.16\CarlaUE4.exe -quality-level=Low -ResX=1280 -ResY=720 -windowed
```

- Sunucu başlatma (penceresiz, test için):

```bash
external\CARLA_0.9.16\CarlaUE4.exe -RenderOffScreen -quality-level=Low -nosound
```

- Bağlantı testi (sunucu açıkken):

```bash
.venv\Scripts\python.exe -c "import carla; c=carla.Client('127.0.0.1',2000); c.set_timeout(10); print(c.get_server_version(), c.get_world().get_map().name)"
```

- **Doğrulandı (26.10.2026):** `carla 0.9.16`, harita `Carla/Maps/Town10HD_Opt`, 23 aktör. `carla` modülünde `__version__` alanı yok; sürüm sunucudan `get_server_version()` ile alınır.

## Bilinen notlar

- Proje venv'i artık 3.12.15; Python 3.15 ve 3.11 sistemde ayrı duruyor, projeye karışmıyor.
- `.venv311.bak\` geri dönüş için duruyor; gerek yoksa silinebilir.
- ASAM 2.2.0 paketi (`grammar.ebnf`, `types.osc`, `domain.osc`, `standard.osc`) `external/asam/` altında yerel olarak duruyor; `external/` `.gitignore` kapsamında. `--stdlib external/asam/standard.osc` ile gerçek kütüphane yükleniyor; gerçek kütüphaneye bağlı testler dosyalar yoksa `skipif` ile atlanıyor.
