"""Merge partial OCF resource representations onto the cached rep.

A physical-panel change arrives as an OBSERVE notify carrying only its own
token (a washer's /course/vs/0 packs cycle, Extra Rinse, and dispenser
dosing into one options array); replacing the array verbatim wipes every
sibling setting to unknown until the next full poll.

Dictionaries merge recursively; options[] merges by token prefix and
items[] by item id; every other list is an atomic snapshot that replaces.
Poll/sweep/direct reads stay on the shallow merge so a full read can still
retire stale tokens.
"""

from __future__ import annotations

OPTIONS_FIELD = "x.com.samsung.da.options"
ITEMS_FIELD = "x.com.samsung.da.items"
ITEM_ID_FIELD = "x.com.samsung.da.id"


def merge_options_tokens(cached: list | None, new_tokens: list | None) -> list:
    """Merge `<Prefix>_<Value>` tokens the way the device does: match by
    prefix, replace if present, append if not."""
    merged = list(cached or [])
    for token in new_tokens or ():
        if not isinstance(token, str) or "_" not in token:
            continue
        prefix = token.split("_", 1)[0]
        replaced = False
        for i, old in enumerate(merged):
            if isinstance(old, str) and old.startswith(prefix + "_"):
                merged[i] = token
                replaced = True
        if not replaced:
            merged.append(token)
    return merged


def merge_items_entries(cached: list | None, new_items: list | None) -> list:
    """Merge items[] entries matched by x.com.samsung.da.id, recursing into
    each matched item so nested fields merge rather than replace. Arrays
    whose entries carry no id (fridge temperatures keyed by description,
    sensors by type) are snapshots, not deltas, so they replace verbatim;
    non-dict entries are ignored as before."""
    incoming = [i for i in (new_items or ()) if isinstance(i, dict)]
    if incoming and all(i.get(ITEM_ID_FIELD) is None for i in incoming):
        return [dict(i) for i in incoming]
    merged: list = [dict(i) if isinstance(i, dict) else i for i in (cached or [])]
    for new_item in new_items or ():
        if not isinstance(new_item, dict):
            continue
        item_id = new_item.get(ITEM_ID_FIELD)
        for i, existing in enumerate(merged):
            if isinstance(existing, dict) and existing.get(ITEM_ID_FIELD) == item_id:
                merged[i] = merge_partial_rep(existing, new_item)
                break
        else:
            merged.append(dict(new_item))
    return merged


def merge_partial_rep(cached: dict, rep: dict) -> dict:
    """Merge a partial rep onto the cached one, recursively.

    Absent keys stay cached; present scalars and non-keyed lists replace;
    nested dicts recurse; options[] merges by token prefix; items[] merges
    by item id. Neither input is mutated.
    """
    merged = dict(cached or {})
    for key, value in (rep or {}).items():
        old = merged.get(key)
        if key == OPTIONS_FIELD and isinstance(value, list):
            merged[key] = merge_options_tokens(old if isinstance(old, list) else None, value)
        elif key == ITEMS_FIELD and isinstance(value, list):
            merged[key] = merge_items_entries(old if isinstance(old, list) else None, value)
        elif isinstance(old, dict) and isinstance(value, dict):
            merged[key] = merge_partial_rep(old, value)
        elif isinstance(value, list):
            merged[key] = list(value)
        elif isinstance(value, dict):
            merged[key] = dict(value)
        else:
            merged[key] = value
    return merged


def _find_token(options: list | None, prefix: str) -> str | None:
    """The `<Prefix>_<Value>` token in `options`, else None."""
    for token in options or ():
        if isinstance(token, str) and token.startswith(prefix + "_"):
            return token
    return None


def _hold_options(candidate: list | None, before: list | None, written: list | None) -> list:
    """Hold written options tokens against a stale echo: restore the written
    token where the candidate shows its pre-write value or the pre-write
    value is unknown, leaving a confirming or third value alone. A written
    token the candidate omits is re-added only when it was never seen before;
    a dropped previously-known prefix is a removal and is respected."""
    result = list(candidate or [])
    for token in written or ():
        if not isinstance(token, str) or "_" not in token:
            continue
        prefix = token.split("_", 1)[0]
        current = _find_token(result, prefix)
        if current == token:
            continue  # confirmed
        old = _find_token(before, prefix)
        if current is None:
            if old is None:
                result.append(token)  # new token the device hasn't reported yet
            continue  # known prefix now omitted by the device: respect the removal
        if old is None or current == old:
            for i, c in enumerate(result):
                if isinstance(c, str) and c.startswith(prefix + "_"):
                    result[i] = token
                    break
    return result


def _hold_items(candidate: list | None, before: list | None, written: list | None) -> list:
    """Hold written items[] fields against a stale echo, per item id,
    recursing into each matched item; a written id the candidate omits is
    re-added only when it was never seen before."""
    out = [dict(i) if isinstance(i, dict) else i for i in (candidate or [])]
    before_by_id = {i.get(ITEM_ID_FIELD): i for i in (before or []) if isinstance(i, dict)}
    for new_item in written or ():
        if not isinstance(new_item, dict):
            continue
        item_id = new_item.get(ITEM_ID_FIELD)
        for i, existing in enumerate(out):
            if isinstance(existing, dict) and existing.get(ITEM_ID_FIELD) == item_id:
                out[i] = hold_written_values(existing, before_by_id.get(item_id), new_item)
                break
        else:
            if item_id not in before_by_id:
                out.append(dict(new_item))
    return out


def hold_written_values(candidate: dict, before: dict | None, body: dict | None) -> dict:
    """Reconcile a merged rep against a write, holding written values the
    candidate would otherwise revert to their pre-write state; a confirming
    or third value passes through, so unrelated changes aren't blocked."""
    if not body or not candidate:
        return dict(candidate or {})
    out = dict(candidate)
    before = before or {}
    for key, new_val in body.items():
        if key == OPTIONS_FIELD and isinstance(new_val, list):
            out[key] = _hold_options(out.get(key), before.get(key), new_val)
        elif key == ITEMS_FIELD and isinstance(new_val, list):
            out[key] = _hold_items(out.get(key), before.get(key), new_val)
        elif isinstance(new_val, dict) and isinstance(out.get(key), dict):
            prev = before.get(key) if isinstance(before.get(key), dict) else None
            out[key] = hold_written_values(out[key], prev, new_val)
        else:
            cur = out.get(key)
            if key in before:
                if cur == before[key]:
                    out[key] = new_val
            elif cur != new_val:
                out[key] = new_val
    return out
