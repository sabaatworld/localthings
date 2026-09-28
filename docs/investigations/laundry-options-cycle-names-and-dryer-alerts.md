# Laundry options, cycle names, and dryer alerts

One PR adds washer Extra Rinse and Soil Level selects, washer and dryer
cycle labels, dryer Damp Alert and Wrinkle Prevent Active entities, and the
AntiStatic/Eco Dry negative. It is a registry, translations, and tests-only
change: no new hrefs and no coordinator or observe changes.

## Washer options and cycle names

### Live evidence (2026-09-25, `read_resource` on both appliances)

- Washer `DA_WM_TP1_21_COMMON` (WF8900B):
  `/course/vs/0` options carry `ExtraRinse_On` plus
  `ExtraRinseSet_F0×14 00 F0×7 00 F0 00`
  (25 entries). The set is positional with the `supportedOptions`
  course records — 25 records at the header-stated 7-byte width, opening
  `01 8C 53 51 5B 57 64 5A 85 54 56 5C 55 66 58 …` — not with the 21-entry
  `editCourseList` below (lengths differ, and edit-order indexing runs
  off the end). The three `00` bytes land on records `58` (Wool), `5F` (Spin Only)
  and `60` (Self Clean+): courses with no rinse phase to extend.
  `Course_01` selected.
  `editCourseList_01 51 5B 57 56 60 8C 53 64 5A 85 54 5C 55 58 68 67
  63 5D 5F 5E` (21 courses), table `Table_02`.
  `/washer/vs/0` carries `soilLevel: Normal` with
  `supportedSoilLevel: [None, ExtraLight, Light, Normal, Heavy,
  ExtraHeavy]`.
- Dryer `DA_WM_TP1_21_COMMON` (DV8900B):
  `editCourseList_012F3E073302061735340E053032`, table `Table_03`,
  `Course_01` selected. No `ExtraRinse*`/`soilLevel` tokens anywhere —
  both selects are washer-only, gated by presence.
- Current symptoms: washer cycle select reads raw `01`, dryer cycle
  select reads raw `01`. The washer `Table_02` catalog lacks the US
  family below; the dryer `Table_03` catalog lacks 7 of the 14 live
  codes.

### Extra Rinse: `SelectDesc` on `/course/vs/0` (`WASHER_COURSE`)

```python
SelectDesc(
    key="extra_rinse",
    translation_key="extra_rinse",  # new catalog entry, states on/off
    entity_category="config",
    options=("On", "Off"),  # static: no supportedExtraRinse list exists
    exists_fn=bool_option_exists("ExtraRinse"),
    rep_fn=lambda rep: option_value(rep.get("x.com.samsung.da.options"), "ExtraRinse"),
    write_fn=...,  # bool_option_write("ExtraRinse") equivalent
    display_fn=None,  # catalog states, not a fallback label
    validate_fn=...,  # supportedOptions-order gate below
)
```

- Read/write reuse `common.option_value` and a
  `bool_option_write("ExtraRinse")`-equivalent write (guards
  `p in ("On","Off")` and a populated options array, posts one token —
  the same prefix-merge contract as `Course`, issue #54). State is
  readable locally (`ExtraRinse_On`/`_Off` observed across reads), so
  the entity reports the live value.
- Presence gates on the token existing at setup
  (`bool_option_exists`), matching bubble-soak/pre-wash/intensive.
- Per-course gate: resolve the selected `Course` against the
  `supportedOptions` record order (the list `ExtraRinseSet` is
  positional with — 25 records, `00` on `58`/`5F`/`60`), reject **On**
  when the byte is not `F0`, never reject **Off**, allow on
  unresolvable data. This deliberately differs from
  `_bool_option_switch`'s `validate_fn`, which indexes
  `cycle_options()` (editCourseList order): the lengths differ here
  (25 vs 21), so edit-order indexing runs off the end. The gate needs a
  small helper beside `_course_records` in `laundry.py` exposing the
  record order; the existing private parser is the split both the
  option masks and this gate must share.
- Rejection surfaces as `extra_rinse_unavailable_for_cycle` (new
  `exceptions` entry, en + 7 locales, mirroring the
  `bubble_soak_unavailable_for_cycle` message shape).
- Select rather than Switch: `On`/`Off` are device-reported option
  values with catalog states (not a boolean toggle), and the approved
  design keeps the two-option select.

### Soil Level: `SelectDesc` on `/washer/vs/0` (`WASHER_SETTINGS`)

Exact mirror of the existing `rinse_cycles` descriptor — field plus
live supported list, no new machinery (`translation_key` defaults to
`key`, as with the other wash controls):

```python
SelectDesc(
    key="soil_level",
    field="x.com.samsung.da.soilLevel",
    icon="mdi:water-opacity",  # same family as the wash-control selects
    entity_category="config",
    options_field="x.com.samsung.da.supportedSoilLevel",
    exists_fn=_wash_control_present("soilLevel"),
    write_fn=lambda p, rep, href=None: (
        ["washer", "vs", "0"],
        {"x.com.samsung.da.soilLevel": p},
    ),
)
```

No `validate_fn`: no per-course availability bitmap for soil was
observed, and `supportedSoilLevel` is already the board's own list.
`_wash_control_present` keeps the phantom-guard other wash controls
have (issue #475).

### Cycle names (translations-only)

Course codes are table-scoped: `Table_02` (washer) and `Table_03`
(dryer) share hex values with different meanings, so washer names are
never borrowed for dryer codes or vice versa.

#### Washer `washer_cycle_table_02` — all 21 verified

Verified against the WF53BB8900A 25-cycle spec sheet, the WF50A8600AV
service manual (WF8000A platform), and Samsung support ANS10001016.
Hex bindings themselves are community/OCF-dump sourced — Samsung never
publishes the hex — but every name below appears verbatim in the
official cycle lists:

| code | name | | code | name |
| --- | --- | --- | --- | --- |
| 01 | Normal | | 54 | Towels |
| 51 | Super Speed | | 5C | Outdoor |
| 5B | Small Load | | 55 | Activewear |
| 57 | Delicates | | 68 | Steam Bulky |
| 56 | Bedding | | 67 | Steam Allergen |
| 60 | Self Clean+ | | 63 | Power Steam |
| 53 | Heavy Duty | | 5D | Power Rinse |
| 64 | Steam Whites | | 5F | Spin Only |
| 5A | Steam Sanitize | | 5E | Rinse + Spin |
| 85 | Steam Normal | | 58 | Wool |
| 5c | Outdoor | | 8C | AI OptiWash |

Normalizations: `Delicates` (plural), `Activewear` (spec spelling),
`Super Speed` (support spelling), `Self Clean+` (keep `+`),
`Rinse + Spin` (spaced). `8C` confirmed 2026-09-25 by dropdown
selection + `Course_8C` readback (it was the one code missing from the
24-cycle marketing list).

Of these, 14 codes are new to the catalog
(`51/5B/56/58/8C/64/5A/85/5C/68/67/63/5D/5F`) and 2 are corrections to
existing entries: `57` reads `Delicate` today, official name is plural
`Delicates`; `5E` reads `Rinse+Spin` today, canonical display is
spaced `Rinse + Spin`. Per-locale change matrix (verified against current files): `57`
changes in en/cs/es/it/sk only (de `Feinwäsche`, ko `섬세의류`, nl
`Fijne was` already match); `5e` changes in en/cs only (de, es, it,
ko, nl, sk already match the spaced form). New code keys
land lowercase (`5b`, not `5B`), matching the existing catalog
convention. `58` Wool reuses each locale's existing Wool rendering
(`washer_cycle_table_02.22`, identical to `dryer_cycle_table_03.0f` in
every locale) — no new translation work.

Washer `01` display: the API state `01` is the translation state key by
design (the frontend localizes it via `washer_cycle_table_02`), and the
live board reports `Table_02` with the catalog entry present — so no
bug is asserted. Investigation step at implementation: confirm the UI
shows Normal; only if it shows raw `01`, capture the resolved
translation key and `translated_states` output before ordering any fix.

#### Dryer `dryer_cycle_table_03` — 7 verified in manuals, 7 confirmed physically

The manual-verified 7 were already in the catalog with matching names
(`01` Normal, `02` AI Dry, `05` Bedding, `06` Time dry, `07` Delicates,
`0E` Towels, `17` Super Speed — `06` keeps the catalog's existing
lowercase-d casing).

The remaining 7 had no English `Table_03` source anywhere, so they were
bound by selecting each raw entry in the dropdown and reading the
panel/app name back (issue #80 method, 2026-09-25):

| code | confirmed name |
| --- | --- |
| 33 | Steam Sanitize+ |
| 32 | Perm Press |
| 35 | Wrinkle Away |
| 34 | Steam Refresh |
| 30 | Activewear |
| 3E | Small Load |
| 2F | Heavy Duty |

Notes: `Perm Press` keeps the panel abbreviation, matching the
existing `dryer_cycle_table_00.9e` rendering (also `washer Table_00`
for the same cycle family); `Activewear` duplicates the existing
`3C` entry's name (same pattern as the `02`/`29` AI Dry pair — no
ambiguity on this board, whose edit list carries `30` but not `3C`);
`Steam Sanitize+` keeps the `+` per the `Self Clean+` precedent and
reuses the `Table_00.9b` rendering shape. All
seven are genuine Samsung US dryer cycles, physically bound — the only
provisional label in either table is washer `8C`.

Dryer unknown-code spacing fix: the live dropdown showed
`3 E` and `2 F` (spurious space). Both families' `cycle_select`
wrap their fallback in `label()`, which returns `None` for unknown
codes, so both fall through `select._display` past the
`translation_key and not known` early return (the key has states) into
the cosmetic camel-split — exactly the path the module comment
describes for a declined fallback. Fix: pass a verbatim fallback
(`lambda value, resources: value`) on the dryer `cycle_select` so
unknown codes render as-is (`3E`, `2F`), like digit-only codes
(`33`/`32`/`35`/`34`/`30`, which never match the camel boundary)
already do. The washer shares the path and gets the same treatment.

Dryer `translation_key` bake-in (found live 2026-09-25): the dryer
dropdown showed raw codes for every option — including the 7 already
catalogued — while the washer resolved. Root cause was not the labels
but the key: the entity registry held `cycle` for `select.dryer_cycle`
(the frontend renders option states under the registry's stored key),
because the entity registered before the cold-tier poll delivered
`/st/dryercourse/vs/0` (dryer setup: ~4s; washer: ~28s with retries —
same race, opposite outcome). Restarts re-bake whatever resolves at
registration, so no restart could heal it. Fix: `poll_tier="probe"` on
`/st/washercourse/vs/0` + `/st/dryercourse/vs/0` in `ignored.py` — the
first-discovery probe runs inside entry setup, so the table is present
deterministically at registration and the next restart self-heals the
registry entry (verified live: `dryer_cycle_table_03` after restart).
Same trap exists for `/st/airdressercourse/vs/0` — left as a follow-up
(washer/dryer scope). The table hrefs stay covered by IGNORED in every
registry, so the probe-coverage test is unaffected.

Out of scope: bubble-soak/pre-soak/intensive (already shipped,
per-course gated, unavailable on this washer — not reworked here).

### Push

Observe subscribes hot/warm hrefs only, and `/course/vs/0` was
cold-tier — so Extra Rinse and cycle changes arrived via cold polls,
not push (verified live: absent from `observe_subscribed_hrefs`).
Fix: `poll_tier="warm"` on `WASHER_COURSE` + `DRYER_COURSE`
(dishwasher/airdresser course capabilities stay cold — their traffic
patterns aren't this PR's to change). Verified live after restart:
`/course/vs/0` subscribed on both washer and dryer. `/washer/vs/0`
(soil) was already observed. No coordinator change.

### Files touched

- `custom_components/localthings/registry/capabilities/washer.py`:
  one `SelectDesc` in `WASHER_COURSE` (extra_rinse + validate),
  one in `WASHER_SETTINGS` (soil_level); `WASHER_COURSE` to warm tier
  (push).
- `custom_components/localthings/registry/capabilities/dryer.py`:
  verbatim fallback + warm tier on `DRYER_COURSE`.
- `custom_components/localthings/registry/capabilities/ignored.py`:
  probe tier on the two course-table hrefs (translation-key bake-in).
- `custom_components/localthings/registry/capabilities/laundry.py`:
  record-order helper beside `_course_records` for the ExtraRinse
  gate; verbatim label fallback used by the dryer (and washer) cycle
  selects.
- `custom_components/localthings/registry/capabilities/dryer.py`:
  verbatim fallback on `DRYER_COURSE`'s `cycle_select`.
- `custom_components/localthings/translations/en.json`: new `extra_rinse`
  name/states (`on`/`off`), `extra_rinse_unavailable_for_cycle`
  exception (`"Extra Rinse isn't available on the selected cycle."`),
  and `soil_level` name/states (`none`, `extra_light`, `light`,
  `normal`, `heavy`, `extra_heavy`), 14 new
  washer `Table_02` states plus the `57`/`5E` corrections, 7 new dryer
  `Table_03` states (`33/32/35/34/30/3e/2f`, physically confirmed).
  No `icons.json` change (`mdi:water-opacity` descriptor icon is the
  mechanism; `icons.json` carries no `select` section).
- `translations/{cs,de,es,it,ko,nl,sk}.json`: best-effort drafts for
  all of the above are prepared (each locale follows its own file's
  brand-term handling — e.g. `AI OptiWash` kept in English where the
  locale keeps `AI Wash`, localized where it translates it). Flagged
  uncertain terms per locale (`Power Steam`/`Power Rinse` phrasing
  everywhere, `Bulky` renderings, soil-scale adjectives, `ko` spacing)
  are for a native speaker to confirm, not blockers.
- `tests/`: fixture refresh from the two live dumps above plus golden
  updates for the two new selects and the relabelled cycles.
- This doc.

### Verification

```sh
.venv/bin/ruff format --check custom_components tests
.venv/bin/ruff check custom_components tests
.venv/bin/ty check custom_components tests
.venv/bin/pytest tests/ -q
```

### What is needed from the physical devices

1. Washer ExtraRinse sweep: select `On`, re-read (`held`), select
   `Off`, re-read; confirm a push notification arrives on
   `/course/vs/0` for each change (observe mode). Try `On` on course
   `58` (Wool), `5F` (Spin Only) or `60` — the `00` bytes — to
   exercise the validate rejection.
2. Washer Soil sweep: write each of `None/ExtraLight/Light/Normal/
   Heavy/ExtraHeavy` on `/washer/vs/0`, re-read each.
3. Washer cycle pass: step through all 21 local courses, confirming
   the new label follows each selection. `8C` — DONE 2026-09-25
   (`Course_8C` read back after selecting the slot).
4. Dryer gap pass — DONE 2026-09-25, bound by dropdown selection +
   panel/app readback: `33` Steam Sanitize+, `32` Perm Press,
   `35` Wrinkle Away, `34` Steam Refresh, `30` Activewear, `3E` Small
   Load, `2F` Heavy Duty. Same method for the 7 verified codes as a
   sanity check.

### Translation record (shipped in this PR)

Catalog keys stay byte-identical (lowercase hex); only display values
are added. `57` changes in en/cs/es/it/sk only; `5e` changes in en/cs
only (verified against current files — all other locales already match
the corrected en). `58` Wool reuses existing renderings (table below).

#### Washer `Table_02` — 14 new, 2 corrected

| code | en | de | ko | cs | es | it | nl | sk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 51 | Super Speed | Super Speed | 쾌속세탁 | Super rychlé | Súper velocidad | Super Speed | Super Speed | Super Speed |
| 5b | Small Load | Kleine Beladung | 소량세탁 | Malá náplň | Carga pequeña | Carico ridotto | Kleine was | Malá náplň |
| 56 | Bedding | Bettwäsche | 이불 | Ložní prádlo | Ropa de cama | Biancheria da letto | Beddengoed | Posteľná bielizeň |
| 58 | Wool | Wolle | 울 | Vlna | Lana | Lana | Wol | Vlna |
| 8c | AI OptiWash | KI-OptiWash | AI 옵티워시 | AI OptiWash | Lavado IA OptiWash | Lavaggio AI OptiWash | AI OptiWash | AI OptiWash |
| 64 | Steam Whites | Dampf-Weißwäsche | 스팀 흰옷 | Parní bílé prádlo | Blancos con vapor | Bianchi a vapore | Stoom witte was | Parná biela bielizeň |
| 5a | Steam Sanitize | Dampf-Hygiene | 스팀 살균 | Parní dezinfekce | Desinfección con vapor | Igienizzante a vapore | Stoomhygiëne | Parná dezinfekcia |
| 85 | Steam Normal | Dampf-Normal | 스팀 표준세탁 | Parní normální | Normal con vapor | Normale a vapore | Stoom normaal | Parný normálny |
| 5c | Outdoor | Outdoor | 아웃도어 | Outdoor | Exterior | Capi outdoor | Outdoor | Outdoor |
| 68 | Steam Bulky | Dampf-Großwäsche | 스팀 이불 | Parní objemné prádlo | Voluminoso con vapor | Voluminosi a vapore | Stoom volumineuze was | Parná objemná bielizeň |
| 67 | Steam Allergen | Dampf-Anti-Allergie | 스팀 알레르기 케어 | Parní antialergenní | Antialérgico con vapor | Antiallergia a vapore | Stoom anti-allergie | Parný antialergénny |
| 63 | Power Steam | Power-Dampf | 강력 스팀 | Výkonná pára | Vapor potente | Vapore potente | Power Steam | Výkonná para |
| 5d | Power Rinse | Power-Spülen | 강력 헹굼 | Výkonné máchání | Aclarado potente | Risciacquo potente | Power spoelen | Výkonné plákanie |
| 5f | Spin Only | Nur Schleudern | 탈수만 | Pouze odstřeďování | Solo centrifugar | Solo centrifuga | Alleen centrifugeren | Iba odstreďovanie |
| 57* | Delicates | Feinwäsche | 섬세의류 | Jemné prádlo | Delicados | Delicati | Fijne was | Jemná bielizeň |
| 5e* | Rinse + Spin | Spülen + Schleudern | 헹굼+탈수 | Máchání + odstřeďování | Aclarar + Centrifugar | Risciacquo+Centrifuga | Spoelen+centrifugeren | Plákanie + odstreďovanie |

#### `extra_rinse` (new key) and `soil_level` (new key)

| | en | de | ko | cs | es | it | nl | sk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| extra_rinse name | Extra rinse | Extra-Spülen | 헹굼 추가 | Extra máchání | Aclarado extra | Risciacquo extra | Extra spoelen | Extra plákanie |
| on | On | Ein | 켜기 | Zapnuto | Encendido | Acceso | Aan | Zapnuté |
| off | Off | Aus | 끄기 | Vypnuto | Apagado | Spento | Uit | Vypnuté |
| soil_level name | Soil level | Verschmutzungsgrad | 오염도 | Stupeň znečištění | Nivel de suciedad | Livello di sporco | Vervuilingsgraad | Stupeň znečistenia |
| none | None | Keine | 없음 | Žádné | Ninguna | Nessuna | Geen | Žiadne |
| extra_light | Extra light | Extra leicht | 매우 약함 | Extra lehké | Extra leve | Extra leggero | Extra licht | Extra ľahké |
| light | Light | Leicht | 약함 | Lehké | Leve | Leggero | Licht | Ľahké |
| normal | Normal | Normal | 보통 | Normální | Normal | Normale | Normaal | Normálne |
| heavy | Heavy | Stark | 강함 | Silné | Intenso | Intenso | Erg vervuild | Silné |
| extra_heavy | Extra heavy | Extra stark | 매우 강함 | Extra silné | Extra intenso | Extra intenso | Extra erg vervuild | Extra silné |

#### Dryer `Table_03` — 7 new (physically confirmed 2026-09-25)

| code | en | de | ko | cs | es | it | nl | sk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 33 | Steam Sanitize+ | Dampf-Hygiene+ | 스팀살균+ | Parní dezinfekce+ | Desinfección por vapor+ | Igienizzante a vapore+ | Stoomhygiëne+ | Parná dezinfekcia+ |
| 32 | Perm Press | Pflegeleicht | 구김방지 | Nežehlivé prádlo | Planchado fácil | Pronto da stirare | Strijkvrij | Nekrčivá bielizeň |
| 35 | Wrinkle Away | Entknittern | 구김제거 | Proti pomačkání | Anti-arrugas | Antipiega | Kreukpreventie | Proti pokrčeniu |
| 34 | Steam Refresh | Dampf-Auffrischung | 스팀 리프레시 | Parní osvěžení | Renovación por vapor | Rinfresca a vapore | Stoom opfrissen | Parné osvieženie |
| 30 | Activewear | Sportkleidung | 피트니스 | Sportovní oblečení | Ropa deportiva | Abbigliamento sportivo | Sportkleding | Športové oblečenie |
| 3e | Small Load | Kleine Beladung | 소량 | Malá náplň | Carga pequeña | Piccolo carico | Kleine was | Malá náplň |
| 2f | Heavy Duty | Intensiv | 강력건조 | Intenzivní | Servicio intensivo | Intenso | Intensief | Intenzívny |

Terms flagged for native-speaker confirmation (non-blocking):
Wrinkle Away phrasing everywhere; `Power Steam`/`Power Rinse`
constructions; `Bulky` renderings; soil-scale adjectives; `ko`
spacing (`소량세탁`, `스팀 리프레시`); exception feature-name choice
(de/nl keep English `Extra Rinse` mirroring `Bubble Soak`, others
localize). `33`/`32`/`2f` reuse existing
`Table_00` renderings (`9b`/`9e`/`9c`) verbatim. Existing dryer codes
(`01/02/05/06/07/0e/17`) verified consistent in all locales — no
changes.

#### `exceptions` — 1 new (mirrors `bubble_soak` sibling shape)

| key | en |
| --- | --- |
| extra_rinse_unavailable_for_cycle | Extra Rinse isn't available on the selected cycle. |

Locales (mirror each locale's `bubble_soak` sibling): cs `Extra
máchání není u vybraného cyklu k dispozici.`; de `Extra Rinse ist bei
dem ausgewählten Programm nicht verfügbar.`; es `El aclarado extra no
está disponible en el ciclo seleccionado.`; it `Risciacquo extra non è
disponibile per il ciclo selezionato.`; ko `선택한 코스에서는 추가
헹굼을 사용할 수 없습니다.`; nl `Extra Rinse is niet beschikbaar voor
het geselecteerde programma.`; sk `Extra plákanie nie je pri vybranom
cykle dostupné.`

### Execution plan

Ordered; each step lands tested before the next begins.

1. `washer.py` — add `extra_rinse` `SelectDesc` to `WASHER_COURSE`
   (`bool_option_write`-equivalent write, `bool_option_exists`,
   supportedOptions-order `validate_fn` via the new `laundry.py`
   record-order helper, `extra_rinse_unavailable_for_cycle` rejection
   key) and warm tier on `WASHER_COURSE` (push). The static `options=("On","Off")` is the documented skill-§6
   exception (no `supportedExtraRinse` field exists on any dump) — not
   a pattern to copy where a supported-values list does exist. New
   comments follow CONTRIBUTING (why-only, 1–2 sentences, cite the
   issue/live observation once).
2. `washer.py` — add `soil_level` `SelectDesc` to `WASHER_SETTINGS`
   (field + `options_field`, `_wash_control_present`, direct write).
3. `dryer.py` + `washer.py` — verbatim label fallback
   (`lambda value, resources: value`) on both cycle selects (fixes
   `3 E`/`2 F`; washer shares the path); warm tier on `DRYER_COURSE`
   (push). `ignored.py` — probe tier on `/st/washercourse/vs/0` +
   `/st/dryercourse/vs/0` (translation-key bake-in); verify the dryer
   registry entry flips to `dryer_cycle_table_03` after restart.
4. `translations/en.json` — add `extra_rinse`, `soil_level`, the
   exception entry, 14 washer states + `57`/`5E` corrections, 7 dryer
   states (tables above).
5. `translations/{cs,de,es,it,ko,nl,sk}.json` — apply the drafted
   values verbatim including the exception entry (tables above); new
   code keys lowercase. (The mirror-shape test enforces key-for-key
   parity — a missing exception entry fails CI.)
6. `tests/` — no new fixture files (the corpus already binds
   `soil_level` on `washer_wa55a7700av`/`washer_flexwash`; nothing
   carries an `ExtraRinse` token, and live dumps stay out of the tree
   rather than landing half-scrubbed): add `soil_level` to those two
   goldens' state keys, and add unit tests below mirroring the
   bubble-soak per-course test (live tokens inline, not fixtures). No
   test asserting translation strings (§7: catalog data is covered by
   `test_translations.py`).
7. Checks (verbatim per `CONTRIBUTING.md`):
   `.venv/bin/ruff format --check custom_components tests`,
   `.venv/bin/ruff check custom_components tests`,
   `.venv/bin/ty check custom_components tests`,
   `.venv/bin/pytest tests/ -q` (full suite — translations-only
   changes still trip the mirror test).
8. Physical verification (items 1–3 above): ExtraRinse
   On→Off→On with `held` + push arrival, `58`/`5F`/`60` validate
   rejection, full Soil sweep, 21-course washer label pass + `8C`
   readback.
9. Open the PR: single PR, this doc linked, translation tables above
    as the review record, flagged terms called out for native speakers.
    Commits carry your name/email as author and committer with no AI
    trailers (CONTRIBUTING commit rules, AGENTS.md).

## Dryer Damp Alert and Wrinkle Prevent Active

Both entities were confirmed live on a DVE53BB8900TA3
(`DA_WM_TP1_21_COMMON`, Table_03). AntiStatic and Eco Dry were probed to a
negative and ship as documented panel-only behavior, not entities.

### Live evidence (2026-09-27, `read_resource` + panel toggles)

Baseline (Course_01 Normal, power off): `/course/vs/0` carries
`MixedLoadBell_Disable`, `MixedLoadBellNoti_Nothing`,
`MixedLoadBellSet_02FFFF…` (20 pairs), `WrinklePreventRunning_Off`,
`WrinklePreventSet_0F×20`; `/washer/vs/0` carries only `wrinklePrevent`,
`waterTemperature`, `dryLevel`, `dryerType`; `/setting/vs/0` is `{}`.

- **Damp Alert = `MixedLoadBell`.** Panel Off -> `MixedLoadBell_Disable`;
  panel On -> `MixedLoadBell_Enable`; panel Off again -> `_Disable`.
  Round-tripped both ways, nothing else moved (`MixedLoadBellNoti_Nothing`
  and the Set bitmap identical throughout). Samsung's own support article
  (ANS10001020) names the two interchangeably ("Mixed Load Bell, Damp
  Alert"), and the DV53BB8900 spec sheet lists all three panel options
  (Damp Alert, AntiStatic, Eco Dry) among its 14.
- **AntiStatic: no OCF trace.** Panel-confirmed On, Normal cycle, power
  on: full cached snapshot diff (every tracked href) shows nothing but
  the clock (`AvailableDelayTime_75` -> `_79`), power state, an
  `editCourseList` MRU reorder (same 15 courses), and `aiCourse`
  false -> true. A second capture mid-cycle (Course_06 Time Dry,
  running, AntiStatic + Eco Dry both On) is equally clean: no new token,
  all four blobs byte-identical.
- **Eco Dry: no OCF trace.** Shown On in the panel photo yet absent from
  the baseline; toggled Off and back with zero diff in `/course/vs/0`
  or `/washer/vs/0` beyond the clock. The board reports no
  `SavingMode_*` tokens at all (other TP1_21 fixtures do), so Eco Dry is
  not that alias on this board.
- **WrinklePreventRunning flips at `finish`.** A 10-minute Time Dry run
  (`DryTime_10`, ExtraLow, remote-started over localthings) went
  drying (09:53) -> cooling (09:58) -> finish (10:03:47) with Wrinkle
  Prevent armed by the owner's HA automation; the finish-phase read
  shows `WrinklePreventRunning_On`, everything else identical. The
  official SmartThings-cloud `dryerWrinklePrevent` binary sensor stayed
  `off` through the entire run including the wrinkle phase (7-day
  history: never `on`), so the local token is the one to read.

Conclusion: AntiStatic/Eco Dry actuate steam/heat inside the micom with
no report-back -- the panel flag never reaches OCF, idle or running.
There is nothing to bind, so they ship as a docstring note (skill §5:
an opaque behavior with no token is a gap for a human, not a guess).
If a future dump surfaces tokens, they get entities then.

### Damp Alert: `SwitchDesc` on `DRYER_COURSE`

```python
SwitchDesc(
    key="damp_alert",
    icon="mdi:bell-ring-outline",
    entity_category="config",
    exists_fn=bool_option_exists("MixedLoadBell"),
    rep_fn=lambda rep: option_value(..., "MixedLoadBell") == "Enable",
    write_fn=_damp_alert_write,  # On->Enable / Off->Disable single token
)
```

- The Enable/Disable vocabulary (not On/Off) is why this is hand-rolled
  instead of `laundry.bool_option_switch`, which only speaks On/Off.
- No `validate_fn`: the `MixedLoadBellSet_` bitmap is positional with
  the `supportedOptions` records (20 pairs for 20 records at the
  header-stated 5-byte width, vs 15 `editCourseList` entries -- the
  ExtraRinseSet trap, decoded live), but `02` vs `FF` has a single
  datapoint (Course_01 reads `02` and takes the option). A wrong
  rejection is worse than an occasional no-op, so per-course gating
  waits for a second capture; the comment says so.
- `MixedLoadBellNoti_*` never moved in any capture; only the state token
  is modelled.

### Wrinkle Prevent Active: `BinarySensorDesc` on `DRYER_COURSE`

Reads `option_value(..., "WrinklePreventRunning") == "On"`, presence-gated
on the token, no `entity_category` (watched status like
`add_wash_indicator`, not diagnostic). No guess flag -- confirmed
end to end at `finish` above.

### Cycle names

None -- Table_03 catalog untouched by this change.

### Push

Both entities live on `DRYER_COURSE`, already `warm` tier (this PR
stack's push fix), so Damp Alert writes and the Running flip arrive via
push like the cycle select.

### Files touched

- `custom_components/localthings/registry/capabilities/dryer.py`:
  `damp_alert` switch + `wrinkle_prevent_active` binary sensor on
  `DRYER_COURSE`; `_damp_alert_write`. The AntiStatic/Eco Dry negative
  remains recorded in this investigation.
- `translations/en.json`: `damp_alert` ("Damp Alert", panel + DV53BB8900
  manual + ANS10001020), `wrinkle_prevent_active` ("Wrinkle prevent
  active", the SmartThings-cloud entity's own `original_name`).
- `translations/{cs,de,es,it,ko,nl,sk}.json`: `damp_alert` --
  de "Signal Mischbeladung" (Samsung DE dryer datasheet),
  ko "다림질 알림" (Samsung Korea support, samsungsvc.co.kr),
  cs "Upozornění na vlhké prádlo", es "Alerta de humedad",
  it "Avviso di umidità", nl "Waarschuwing vochtige was",
  sk "Upozornenie na vlhké prádlo" (best-effort drafts following each
  file's alert-noun convention, for a native speaker to confirm, not
  blockers); `wrinkle_prevent_active` reuses each locale's Wrinkle
  prevent rendering + its `*_active` suffix convention
  (de "Knitterschutz aktiv", ko "구김 방지 작동 중", ...).
- `tests/test_dryer_capabilities.py`: both keys in expected entities;
  `TestDampAlert` (presence gate, Enable/Disable read, On/Off write
  mapping, bogus + empty-rep rejection); `TestWrinklePreventActive`
  (presence gate, On/Off read). No translation-string assertions (§7:
  `test_translations.py` owns the catalog invariants).
- `tests/fixtures/golden/dryer{,_dve50a8600,_dv6800n,_tp1_21_drum_clean,_dv80h}.json`:
  +`damp_alert`, +`wrinkle_prevent_active` (all five fixtures carry
  both tokens; all read False/Off).
- This doc.

### Verification

```sh
.venv/bin/ruff format --check custom_components tests
.venv/bin/ruff check custom_components tests
.venv/bin/ty check custom_components tests
.venv/bin/pytest tests/ -q
```

### What was needed from the physical device (all done 2026-09-27)

1. Damp Alert On -> re-read (`Enable`) -> Off -> re-read (`Disable`).
2. AntiStatic On (panel-confirmed, Normal) -> full-snapshot diff (clean).
3. Eco Dry Off -> diff (clean) -> back On (default restored).
4. Remote-started 10-min Time Dry (AntiStatic + Eco Dry On, ExtraLow):
   mid-cycle capture (clean) + finish-phase capture
   (`WrinklePreventRunning_On`). Dryer stopped afterwards.
