# Case Study: The Test Suite That Was Too Slow To Run

**Date:** 24 July 2026  
**Result:** Fast suite 15m 46s → 8.5s  
**Also found:** the 82 vs 83 chunk discrepancy, open since early July

---

## Framing: this was not a bug

Every test passed. Every test was correct. Nothing produced a wrong answer.

The defect was that the suite took **15 minutes and 46 seconds**, which in practice means you stop running it. A test suite you avoid running provides no safety at all, however correct it is.

So this is a performance defect in the test harness, not a bug in the system—worth being precise about, because the fix is different in kind. Nothing was repaired. Work that was being done repeatedly was made to happen once.

---

## The symptom

```
85 passed, 1 deselected in 946.89s (0:15:46)
```

The project's stated test architecture is pure-core / impure-shell: pure logic tested in milliseconds, slow integration tests run deliberately. The 29 agent tests already demonstrated this—fully mocked, 0.19 seconds.

So the architecture was right and the suite still took a quarter of an hour. Something was not matching the design.

---

## Measuring instead of guessing

```bash
pytest tests/ -m "not integration" --durations=20
```

`--durations` prints the slowest tests. The output split cleanly into two groups, and the distinction between them turned out to be the whole story.

**Group 1—time in `setup`:**

```
110.61s setup  test_retrieve_returns_cosine_distance
 98.89s setup  test_index_chunks_creates_collection
 98.62s setup  test_retrieve_returns_expected_document
 90.61s setup  test_retrieve_with_filter
```

**Group 2—time in `call`:**

```
217.10s call  test_idempotency
107.40s call  test_store_and_search
107.07s call  test_search_with_filter
105.43s call  test_vector_count_matches_chunk_count
```

And once setup was done, the tests themselves:

```
1.46s call  test_retrieve_returns_expected_document
1.13s call  test_retrieve_with_filter
```

Under two seconds. The tests were never slow. The setup was.

---

## Cause 1: a fixture doing the same work eight times

```python
@pytest.fixture
def indexed_chunks(temp_chroma, corpus_path, expected_chunks):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)
    index_chunks(chunks)
    return chunks
```

No `scope` argument, so pytest defaults to function scope: the fixture runs fresh for every test that requests it.

Embedding 82 chunks through nomic-embed-text on CPU costs roughly 100 seconds. Four tests used the fixture. Four identical embedding passes, ~400 seconds, for one corpus that never changed between them.

**Fix—session scope:**

```python
@pytest.fixture(scope="session")
def indexed_chunks(temp_chroma, corpus_path, expected_chunks):
    ...
```

One complication. `temp_chroma` used pytest's `monkeypatch` fixture, which is function-scoped and cannot be consumed by a session-scoped fixture. The replacement is to instantiate it directly and undo it manually:

```python
@pytest.fixture(scope="session")
def temp_chroma():
    mp = pytest.MonkeyPatch()
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    mp.setattr("src.vectorstore.CHROMA_PATH", temp_path)
    yield temp_path
    mp.undo()
    shutil.rmtree(temp_dir)
```

**The tradeoff, stated plainly:** function scope exists for isolation. Every test gets a clean store, so no test can affect another. Session scope trades that away for speed. Acceptable here because these tests read from the store rather than corrupting it—and because a suite nobody runs is worse than a small isolation risk.

Result: 15m 46s → 11m 25s. The four setup calls collapsed into one.

---

## Cause 2: a test embedding 82 chunks to count to 82

The `call`-time group could not be fixed by scoping, because the work was happening inside the test bodies.

```python
def test_vector_count_matches_chunk_count(corpus_path, expected_chunks):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)
    chunks_with_vectors = embed_chunks(chunks)
    assert len(chunks_with_vectors) == expected_chunks
```

110 seconds. Read the assertion: it checks that `embed_chunks` returns one vector per chunk it was given. It never inspects a single vector.

That property does not depend on corpus size. Five chunks prove it as well as 82.

```python
def test_vector_count_matches_chunk_count(corpus_path):
    docs = load_documents(corpus_path)
    chunks = chunk_documents(docs)
    sample = chunks[:5]
    chunks_with_vectors = embed_chunks(sample)
    assert len(chunks_with_vectors) == len(sample)
```

110s → 4.67s.

`expected_chunks` drops out of the signature, and the assertion gets better for it: the real property is "same number out as in," not "82." The old version was coupled to a corpus-size constant it had no reason to know about.

The pattern was already present in the same file—`test_vector_contains_floats` used `chunks[:1]` and ran in 1.5 seconds. It just had not been applied consistently.

---

## Cause 3: genuinely slow tests were not labelled

Three tests could not be shrunk. `test_store_and_search`, `test_search_with_filter` and `test_idempotency` need a fully populated store, because that is the thing under test. `test_idempotency` indexes the corpus twice on purpose—indexing twice is the behaviour it verifies.

These are not fast tests and never will be. They needed a label, not an optimisation.

```ini
[pytest]
markers =
    slow: embeds the corpus, needs Ollama
    integration: full end-to-end run across components
```

Applied to those three, plus the four tests that consume `indexed_chunks`—any test using that fixture embeds the corpus by definition, so all seven are slow regardless of which file they live in.

Three speeds instead of two:

```bash
pytest -m "not slow and not integration"   # 8.5s   - run constantly
pytest -m "slow"                            # ~5 min - before committing
pytest -m "integration"                     # ~100 min - deliberately
```

The middle tier is the one that was missing. Previously "not integration" meant 15 minutes, so the only real choice was 15 minutes or nothing.

---

## Result

| Stage | Time |
|---|---|
| Start | 15m 46s |
| After session-scoped fixtures | 11m 25s |
| After rewriting the count test | ~9m |
| After marking slow tests | **8.5s** |

78 tests run by default. 8 parked behind markers.

---

## The side finding: 82 vs 83

`conftest.py` states the corpus produces 82 chunks:

```python
@pytest.fixture(scope="session")
def expected_chunks():
    return 82
```

`test_total_chunks_matches_expected` passes, so chunking really does produce 82.

The live store at `data/chromadb` holds **83**.

This discrepancy had been open since early July with no explanation. It is now explained: the corpus is correct, and the live store contains one orphan chunk left over from an earlier ingest—a document that was later changed or removed without the store being rebuilt.

A clean re-index resolves it. Worth doing before further calibration work, since a stale chunk can surface in retrieval results and quietly distort a measurement.

---

## What this is a story about

**Correct is not the same as usable.** Every one of these tests passed and asserted something true. The suite still failed at its actual job, which is to be run often enough to catch regressions early.

**Measure before optimising.** The `setup` versus `call` split in the `--durations` output pointed straight at two different causes needing two different fixes. Guessing would have found the fixture and missed the tests that embedded the corpus in their own bodies.

**Ask what a test is actually asserting.** The 110-second count test was verifying a property that had nothing to do with corpus size. The cost came from habit, not necessity.

**Some slowness is real and should be labelled, not hidden.** Three tests genuinely need a populated store. The fix was a marker, so they can be run deliberately rather than skipped by accident.

---

## Reproduction

```bash
pytest tests/ -m "not slow and not integration" --durations=10
```