# C4z: raw metadata default audit and fresh offline normalization

This package traces the exposed `streamlit.button` 1.49 `type`/`disabled`
inconsistencies to pinned upstream generated metadata and the legacy preparation
policy. Version1.39 is a source control. It creates a fresh signature-default
derivation; it never patches an old source, index, candidate, proposal or runtime.

- [Persian explanation and limits](../../docs/core-raw-defaults.fa.md)
- [Exact changed headers](comparison.fa.md)
- [Protocol](protocol-v1.json): recorded after the raw trace/first implementation,
  before integrated replay; not a blind model preregistration.
- [Complete two-record raw snapshot](raw-api-snapshot-v1.json)
- [Full-file/source/seed provenance](source-provenance-v1.json)
- [Source-aware receipt](source-replay-v1.json): full raw membership and pinned
  Python declaration AST checked in that run.
- [Portable receipt](portable-replay-v1.json): neither external-file check claimed.
- [Verification](verification-v1.json): tests, review, preservation and local logs.

## Reproduce without a provider

From the repository root, choose a new receipt path; the writer refuses overwrite:

```bash
uv run --no-env-file python experiments/core_raw_defaults_v1/replay.py \
  --output /tmp/core-raw-defaults-portable-new.json
```

To authenticate the external raw-file bytes and both JSON pointer entries, add
`--raw-document /path/to/pinned-docs/python/streamlit.json`. To verify the declared
defaults in the pinned implementation without executing it, additionally pass
`--implementation-source /path/to/pinned/button.py`. These files must match the
full physical SHA pins in `source-provenance-v1.json`. The script never downloads
anything. A bundled snapshot alone does not prove external file membership.

Neutral tests use authored data or the already exposed source replay:

```bash
uv run --no-env-file pytest -q tests/test_core_raw_defaults.py \
  tests/test_core_raw_defaults_review.py tests/test_core_raw_default_replay.py
```

## Boundaries

`normalization.py` preserves canonical full raw JSON and full legacy text, patches
only explicit default-header spans, and binds a fresh ID to provenance plus input/
output hashes. Required parameters lose a bogus default; explicit literal `None`
remains distinct from missing/null metadata and unresolved sentinels. Unsupported
grammar rejects without executing expressions. The validator recomputes the whole
strictly typed report. Line coordinates are Unicode offsets into supplied text,
not claimed external file offsets.

The derived text is **not complete raw documentation**: legacy extraction omitted
plural `examples` and nested deprecation content. Those remain in canonical JSON.
Prose contradictions remain untouched. Caller declarations are content-bound,
not authority; pure normalization keeps `raw_membership_authenticated=false`.
The replay verifies external membership separately when full bytes are supplied.
Documentation signatures and pinned Python declarations do not prove installed
runtime behavior, semantic support, model choice, human usefulness or action
permission. All prior8attempts/7finals remain historical, unchanged.

No provider, ledger, current source/build, prompt, factory or UI change; no held-out
payload use. Preserve C4x/C4y bytes, frozen95, the21funded files,117-file watch and
session halt/holds. A future adoption needs fresh corpus/config/financial pins and
human review, without overwriting this or historical receipts.
