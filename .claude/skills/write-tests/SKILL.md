---
name: write-tests
description: Write, add, or create unit tests for this project. Use this skill whenever the user mentions tests, testing, unit tests, test file, write a test, add tests, test coverage, test this function, or asks to verify behaviour with a test. Also triggers when fixing a bug that should have a regression test, or when a new function is added and tests seem warranted.
---

# Writing Tests

Tests live in `tests/`. Run with `.venv/bin/python -m pytest`.

## Rules

**One test = one key behaviour.** Each test should prove a single invariant that would silently break without it. Name it after what it proves, not what it calls — `test_proper_noun_mid_sentence_does_not_split` not `test_find_sentence_end`.

**Fewer is better.** Before adding a test, ask: if this broke, would another test catch it? If yes, skip it. Only test things that are genuinely load-bearing and not covered elsewhere.

**Never modify existing tests** without flagging the user first and getting explicit confirmation. Existing tests are a contract. If a change makes an existing test wrong, tell the user and wait.

## Before writing

1. Read the function under test — understand its invariants, not just its signature.
2. Identify the 1–3 behaviours most likely to silently regress. Those are your tests.
3. Check `tests/` — don't duplicate coverage that already exists.

## Test structure

```python
def test_<what_it_proves>():
    # minimal setup — inline data, no fixtures unless shared across 3+ tests
    result = fn(...)
    assert result == expected
```

Keep setup inside the test unless it's shared. Use a module-level dataclass or namedtuple for word/token stubs rather than dicts — it reads like the real type.

## After writing

Run the suite and confirm all tests pass:

```bash
.venv/bin/python -m pytest tests/ -v
```

Report: how many tests added, what each one proves, and the pass count.
