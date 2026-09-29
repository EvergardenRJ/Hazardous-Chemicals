# Legacy database import

This directory holds private imported data on the server. Git tracks only this
README. The import command is:

```bash
cd /root/autodl-tmp/chemical_kb
python -m scripts.legacy_import --source /path/to/hazmat_ai_service.db
python scripts/kg/knowledge_ops.py build-index
```

The importer reads the source database without modifying it. It copies only
documents, versions, chunks, entities, and relationships into
`hazmat_legacy.sqlite`. It excludes `app_config` (which may contain API keys),
`index_jobs`, and `knowledge_bases`. It writes `chunks_metadata.json` for
keyword retrieval and document listing. These generated files are private and
must stay out of GitHub.

The old 1024-dimensional vectors came from `text-embedding-v4`; they are kept
in the private database for traceability but are not mixed with the current
BGE-M3 vector index. When the current full-corpus extraction releases the GPU, run:

```bash
python -m scripts.legacy_reembed --batch-size 16
```

The job resumes from `reembed.sqlite` and writes a separate `faiss.index`.
The hybrid retriever then searches both BGE-M3 vector indexes. Re-embedding
is required before vector retrieval works for imported chunks.

Recover possible source passages with:

```bash
python -m scripts.legacy_relation_audit
```

This pass finds co-occurring entity names and flags the relation for semantic
review; it never approves a relation. At initial run, 74 had candidate
passages and 3,539 lacked any source passage. None matched an old source
chunk ID. All 20 old predicate labels are absent from the current schema,
so schema mapping and semantic review are required.

All 3,613 old relationships start as `unreviewed` in
`legacy_relation_audits`. Their old source-chunk references do not resolve to
the current chunk rows. Review must recover source evidence, validate the
schema and direction, and check semantics before any relationship is
published as approved. Merely sharing entity names in a chunk is not
sufficient evidence. Existing graph counts will not increase on import.

Import inventory at initial inspection: 152 documents, 7,927 chunks,
1,994 old entity rows and 3,613 old relationship rows. The private
`manifest.json` records the actual source checksum and output counts.


When GPU extraction has stopped, review the 74 source candidates privately:

```bash
python -m scripts.legacy_semantic_review --dry-run
python -m scripts.legacy_semantic_review
```

The semantic reviewer requires an exact source quote containing both endpoints,
a current-schema domain/range match, and a second independent judgment. Any
approved revisions are saved in ignored `data/legacy/reviewed.jsonl` and appear
in the graph and relation editor. The old source database and all derived
content remain on the server. Manual edits of legacy relations also remain in
this private review file. Back up this file and the SQLite database before
turning off the server.
