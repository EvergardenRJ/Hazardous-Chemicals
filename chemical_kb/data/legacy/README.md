# Legacy corpus: server-only data manifest

GitHub tracks this manifest and import/review code only. The private corpus and
all generated indexes, candidates and review results live under
`chemical_kb/data/legacy/` on the server. The persistent backup is
`/autodl-fs/data/alpha-legacy-import/`.

## What the old database contains

`hazmat_ai_service.db` contains 152 document records: 132 DOCX, 12 DOC,
7 PDF and 1 Markdown. These are recorded source types. The database stores
their extracted **body text** in `document_versions.content`, but it does
not contain the original DOCX, DOC, PDF or Markdown binaries. It also holds
7,927 old chunks, 1,994 entity rows, 3,613 relationship rows and 1024
dimensional `text-embedding-v4` vectors.

Import without changing the source file:

```bash
cd /root/autodl-tmp/chemical_kb
python -m scripts.legacy_import --source /path/to/hazmat_ai_service.db
python -m scripts.legacy_body_rechunk
python scripts/kg/knowledge_ops.py build-index
```

The importer excludes `app_config` (which may contain API keys),
`index_jobs` and `knowledge_bases`. It writes a sanitized private SQLite
database, old chunk metadata and a private checksum manifest. The public
keyword index contains only the original project's chunks; old chunks go to
the ignored `data/legacy/keyword.sqlite`. Document listing and search query
both sets. The old vectors are never mixed into the BGE-M3 index.

## Recheck the old relationships

```bash
python -m scripts.legacy_relation_audit
python -m scripts.legacy_semantic_review --dry-run
```

Evidence recovery searches both old chunks and all 152 stored document
bodies. It does not approve anything. The 2026-09-29 pass found candidate
passages for 110 of 3,613 old relationships: 74 in old chunks and 110 in
document bodies. The other 3,503 lacked nearby endpoint names in either
source. None of the old source chunk IDs resolved. All old predicate labels
need mapping to the current schema. The candidate counts are **not** approved
graph counts.

After the main GPU extractor releases the model, run
`python -m scripts.legacy_semantic_review`. A relation is approved only
after an exact quote containing both endpoints, current-schema domain/range
validation and a second semantic judgment. The quote may come from a stored
document body. Approved records and later manual edits stay in ignored
`data/legacy/reviewed.jsonl`; the Explorer can display the body source.

## Extract relationships from the complete old document bodies

The original 7,927 chunks remain available for keyword search and audit.
The 2,775 overlapping full-body windows also enter the private keyword index.
Together they cover all 152 stored document bodies. Some body evidence was
absent from the old chunks, so graph extraction uses the overlapping windows
over
`document_versions.content` instead:

```bash
python scripts/kg/extract_corpus.py --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --dry-run
```

After the main corpus GPU job finishes, run the same extraction command
without `--dry-run`, adding `--batch-size 4`. It resumes queued body
windows. Retry failures with `--retry-failed`. Then review and publish:

```bash
python scripts/kg/audit_corpus_candidates.py --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --static-only
python scripts/kg/audit_corpus_candidates.py --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --batch-size 4
python -m scripts.legacy_publish_corpus --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite --dry-run
python -m scripts.legacy_publish_corpus --metadata data/legacy/body_chunks_metadata.json --db data/legacy/body_corpus.sqlite
```

Publication requires passing extraction validation, exact body source
evidence, semantic audit and current-schema validation. The previously
initialized `data/legacy/corpus.sqlite` queue for old chunks is retained
for traceability; `body_corpus.sqlite` is the complete-body extraction
checkpoint.

## Vector retrieval and graph sync

When the GPU is free, run
`python -m scripts.legacy_reembed --batch-size 16`. This resumes from
`reembed.sqlite` and writes an ignored BGE-M3 `faiss.index` for the
2,775 complete-body windows. The hybrid retriever searches both BGE-M3 indexes.

After publishing reviewed relations, run
`python scripts/kg/sync_to_neo4j.py` if Neo4j is available. It reads
the current private review revisions and removes legacy edges later
rejected. The Explorer page reads the private review file directly.

Back up the sanitized database, body and old-chunk metadata, corpus
checkpoints, private keyword/vector indexes and `reviewed.jsonl` to
`/autodl-fs/data/alpha-legacy-import/`. Never add these private files
to GitHub.
