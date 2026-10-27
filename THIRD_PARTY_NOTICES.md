# Third-Party Notices

OSC2C is licensed under the MIT License (see [LICENSE](LICENSE)). This file
lists third-party components, their licenses, and the modifications made to
them.

## 1. PMSF py-osc2 grammar and generated parser — MPL-2.0

Files covered:

- `grammar/openscenario2.g4`
- `src/osc2c/frontend/generated/*.py`

Copyright (C) 2021–2024 PMSF IT Consulting Pierre R. Mai.

The grammar is a modified version of the ASAM OpenSCENARIO 2 grammar from
[PMSF py-osc2](https://github.com/PMSFIT/py-osc2), licensed under the Mozilla
Public License 2.0 (MPL-2.0). The generated parser files are produced from
that grammar with ANTLR 4.13.2.

Modifications:

- top-level `use` statement support
- spaced physical literals (for example `35 kph`)
- regeneration with ANTLR 4.13.2
- project-specific indentation helper

The MPL-2.0 applies to these files only. A copy of the license is provided in
[LICENSES/MPL-2.0.txt](LICENSES/MPL-2.0.txt) and at
https://mozilla.org/MPL/2.0/.

## 2. ANTLR 4.13.2 tool — BSD-3-Clause

File: `tools/antlr-4.13.2-complete.jar`

Copyright (c) 2012-2022 The ANTLR Project. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

Source: https://www.antlr.org/

## 3. Runtime dependencies — not vendored

These packages are installed from PyPI and are not included in this
repository. They remain under their own licenses:

| Package | Version | License | Copyright |
| --- | --- | --- | --- |
| `antlr4-python3-runtime` | 4.13.2 | BSD-3-Clause | The ANTLR Project |
| `py_trees` | 2.6.0 | BSD-3-Clause | Daniel Stonier |
| `numpy` | — | BSD-3-Clause | NumPy Developers |

## 4. ASAM OpenSCENARIO 2.2.0 standard files — not redistributed

The ASAM OpenSCENARIO DSL 2.2.0 files (`grammar.ebnf`, `types.osc`,
`domain.osc`, `standard.osc`) are not included in this repository. They are
used locally under `external/asam/`, which is excluded from version control.
Users must obtain these files under the terms of the ASAM license.

## 5. CARLA simulator — not redistributed

The CARLA simulator is not included in this repository. It is installed
separately under `external/CARLA_0.9.16` and remains under its own license.

## 6. Referenced paper — cited, not redistributed

The paper *Compiling OpenSCENARIO 2.1 for Scenario-Based Testing in CARLA*
(Gamage and Gamage, arXiv:2604.16452) is cited for attribution. No part of the
paper is redistributed in this repository.
