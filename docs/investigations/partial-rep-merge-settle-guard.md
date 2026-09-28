# Partial-representation merge + value-aware settle guard

Single PR: two fixes to the observe cache layer. Both concern how partial
OCF representations are merged onto the cached state, and both were exposed
live on the same washer (a `DA_WM_TP1_21_COMMON`, WF8900B) once its course
resource moved to warm-tier push.

This branch was carved out of the washer/dryer select work: the merge fix
and this settle-guard fix live here, so the select/cycle-name PR stays
registry- and translations-only.

---

## 1. Partial-representation merge (the "unknown flip-flop")

### Live evidence (2026-09-27)

- Changing Detergent Dispensing on the physical panel sent an OBSERVE
  notify for `/course/vs/0` carrying only
  `options: ["DetergentLevelCtrl_0"]`.
- The old shallow per-field merge replaced the whole cached options array
  with that one token, so Cycle, Extra Rinse, softener dosing and
  drum-clean entities read `None` and rendered `unknown` for ~30s, until a
  full poll restored them.
- A cache-only `read_resource` (no href) showed the one-token array; a live
  GET of `/course/vs/0` returned the full array and healed every entity.
  Confirmed the device is fine — only the cache was wrong.

### Design

New `registry/partial_merge.py` is the single home for partial-rep merge
semantics (the old `common.merge_options_field`/`merge_items_field`
delegate to it for backwards compatibility):

- `merge_partial_rep(cached, rep)` — recursive merge:
  - absent keys stay cached;
  - nested dicts recurse at any depth;
  - `x.com.samsung.da.options` merges by token prefix
    (`merge_options_tokens`: match `<Prefix>_<Value>`, replace if present,
    append if not);
  - `x.com.samsung.da.items` merges by `x.com.samsung.da.id`
    (`merge_items_entries`: merge into the matching item recursively,
    append new ids);
  - every other list/scalar replaces atomically;
  - neither input is mutated — lists/dicts on the replace path are copied,
    so the merged result never aliases the caller's containers.
- Id-less items arrays (fridge temperatures keyed by `description`, sensors
  by `type`) are snapshots, not deltas: when no incoming item carries an
  id, the incoming list replaces verbatim instead of mis-merging one slot's
  reading into another.

Source routing in `observe.py::apply`:

| source | merge |
| --- | --- |
| `observe` / `optimistic` | `merge_partial_rep` (partial, recursive) |
| `poll` / `sweep` / direct read | shallow top-level `{**cached, **rep}` |
| `/alarms/vs/*` (any source) | full replace (absent `items` means cleared) |

Poll/sweep/direct reads stay on the shallow merge so a full read remains
authoritative and retires stale tokens; only partial sources recurse.

`coordinator.py::async_send_command` drops its duplicated optimistic
options/items pre-merge — the optimistic apply now merges centrally through
`apply(source="optimistic")`, and the wire `body` stays minimal (issue #54).

### Preserved behavior

Issue #27 (partial field reps), #54 (single-token writes), #348 (alarms
full-replace), #177 (subdevice href translation) are all unchanged; only
the merge depth for partial sources changed.

---

## 2. Value-aware settle guard (delayed Cycle updates)

### Live evidence (2026-09-27)

After every integration write, `async_send_command` arms a settle guard on
the written href for `_POST_TIMEOUT_S (8s) + _POLL_TIMEOUT_S (35s) = 43s`.
The guard was href-wide and value-blind: it dropped *every* incoming update
for the href, including a physical-panel change to a *different* token.

The "Washer Extra Rinse" automation writes Extra Rinse on every Cycle
change, so each panel Cycle change re-armed the 43s guard. Debug log showed
the pattern:

```
13:11:30.177  cycle changed (physical) → HA cycle state updated
13:11:30.742  PUT /course/vs/0 → 0x44          ← automation re-writes Extra Rinse
13:11:33.618  dropping sweep update for /course/vs/0 (settling)
13:11:41.379  dropping poll  update for /course/vs/0 (settling)
13:11:50.402  dropping poll  update for /course/vs/0 (settling)
13:11:58.594  dropping poll  update for /course/vs/0 (settling)
              ... 43 seconds of dropped pushes ...
```

A Cycle change made at 13:07:45 only landed at 13:08:28 (43s later),
recovered by the sweep. Extra Rinse looked fast only because the
automation's own optimistic write showed immediately, masking the same drop.

### Invariant

> After writing `V_new` to token `T` (previously `V_old`), suppress only
> updates that set `T` back to `V_old` — never anything else.

### Design

Make the guard value-aware and per-token.

`ObserveManager` gains `_settle_guards: dict[href, list[(body, before,
until)]]` (guarded by `_settle_lock`), and `mark_write_pending` grows a
`body`/`before` signature:

```
mark_write_pending(href, settle_s=DEFAULT_SETTLE_S, body=None, before=None)
```

`async_send_command` captures `before = self._cache.get(write_href) or {}`
*before* the optimistic apply, then arms the guard with both `body` and
`before` (both the primary and the reconnect-retry call sites).

During the settle window `apply()` no longer returns early. It merges
normally, then runs `_hold_written(href, merged)` → `hold_written_values`
and applies the held result.

`hold_written_values(candidate, before, body)` reconciles each written key:

| candidate value for a written key | action |
| --- | --- |
| `== V_old` (stale echo) | restore `V_new` (hold) |
| `== V_new` (confirmed) | accept |
| third value (user changed again) | accept |
| unknown old (`key not in before`) and `!= V_new` | restore `V_new` (hold) |

The same rule applies per options token (`_hold_options`, matched by
prefix) and per items entry field (`_hold_items`, matched by id, recursing
into each item), and recurses into nested dicts. Two nuances:

- The "unknown old → hold" fallback keeps a write to a never-yet-read field
  from being reverted by a stale read — at the cost of masking a genuine
  third value for that token until the settle window lapses (bounded,
  accepted).
- A written token/item the stale candidate *omits* is re-added only when it
  was never seen before; a dropped previously-known prefix/id is a device
  removal and is respected (not re-added).

Overlapping writes to the same href stack as separate guard records; a
newer write to a token supersedes because its `before` is the value that
was cached at that write's time (the previous optimistic value). Expired
records are pruned on the next `apply`.

### Preserved behavior

The guard still prevents the issue #9 revert-then-reapply (a stale echo of
the written token is held), and still lets a second integration write land
during the first's window (`source="optimistic"` bypasses the hold). Issue
#294 reconnect/retry, #17/#53 target-href, and #177 subdevice translation
are unaffected.

---

## Files touched

- `custom_components/localthings/registry/partial_merge.py` (new):
  `merge_partial_rep`, `merge_options_tokens`, `merge_items_entries`,
  `hold_written_values`, `_hold_options`, `_hold_items`.
- `custom_components/localthings/observe.py`: partial-source merge routing;
  `_settle_guards` + value-aware `mark_write_pending`/`_hold_written`;
  `apply()` holds instead of dropping.
- `custom_components/localthings/coordinator.py`:
  `async_send_command` captures `before`, passes `body`+`before` to both
  `mark_write_pending` call sites, drops the duplicated pre-merge.
- `custom_components/localthings/registry/capabilities/common.py`:
  `merge_options_field`/`merge_items_field` delegate to partial_merge.
- `tests/localthings/test_observe.py`, `tests/test_coordinator_send_command.py`,
  `tests/localthings/test_coordinator.py`: regression tests (below).

---

## Tests

`tests/localthings/test_observe.py`:

- one-token OBSERVE delta preserves washer siblings;
- nested dict delta preserves sibling fields;
- items[] delta merges recursively by id;
- id-less items replace verbatim;
- ordinary lists replace while absent fields survive;
- poll array stays authoritative;
- sweep array stays authoritative;
- optimistic one-token delta merges;
- no caller-container aliasing;
- settle holds a stale echo of the written options token;
- settle lets an unrelated token change through;
- settle accepts a third value for the written token;
- settle holds a stale scalar field;
- settle holds a written token absent from a stale candidate;
- settle holds a written item absent from a stale candidate;
- settle holds a nested-dict write field;
- settle guard expires and a stale echo then applies;
- guard without body holds nothing.

`tests/test_coordinator_send_command.py`:

- end-to-end: a one-token write posts the minimal body while the cache
  keeps every sibling (driven through `async_send_command`).

`tests/localthings/test_coordinator.py`: existing settle-guard tests
(optimistic apply target href, stale confirm poll, second-write-during-
settle, subdevice translation) all still pass unchanged.

---

## Execution plan

Ordered; each step lands tested before the next begins.

1. `registry/partial_merge.py` — merge + hold helpers (this PR's core).
2. `observe.py` — partial-source routing, then the value-aware guard.
3. `coordinator.py` — capture `before`, pass `body`/`before`.
4. `common.py` — delegate the two merge helpers.
5. Tests — write the new tests first (they fail against the old guard),
   update the two old "drop everything" tests to the new semantics.
6. Checks (verbatim per `CONTRIBUTING.md`):
   `.venv/bin/ruff format --check custom_components tests`,
   `.venv/bin/ruff check custom_components tests`,
   `.venv/bin/ty check custom_components tests`,
   `.venv/bin/pytest tests/ -q`.
7. Physical verification (below).
8. Open the PR with this doc linked. Commits carry your name/email as
   author and committer with no AI trailers (CONTRIBUTING commit rules,
   AGENTS.md).

---

## Physical verification needed

1. Partial-merge: change Detergent Dispensing on the panel and confirm no
   sibling entity flaps to `unknown` — DONE 2026-09-27 live (`00` → `02`,
   zero entities touched `unknown`, cached array stayed complete).
2. Settle guard: with the "Washer Extra Rinse" automation enabled, change
   the Cycle on the panel twice within a few seconds and confirm the second
   change lands within ~seconds (not ~43s), while Extra Rinse still applies
   exactly once per cycle (no revert-then-reapply).
3. Id-less items assumption (unconfirmed): the merge treats id-less items
   arrays (fridge temperatures keyed by description, sensors by type) as
   complete snapshots on notify, so a partial notify replaces the array.
   Confirm on a fridge/sensor board that its notifies always carry the full
   array; if any sends a partial one, that family needs its own keying.

---

## Verification

```sh
.venv/bin/ruff format --check custom_components tests
.venv/bin/ruff check custom_components tests
.venv/bin/ty check custom_components tests
.venv/bin/pytest tests/ -q
```
