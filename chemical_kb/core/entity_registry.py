# -*- coding: utf-8 -*-
"""Reviewed global entity aliases; source assertions remain immutable."""
import json
from datetime import datetime, timezone
from pathlib import Path
from core.config import BASE_DIR


class EntityRegistry:
    def __init__(self, path=None):
        self.path = Path(path or BASE_DIR / "data/kg/entity_aliases.jsonl")

    def records(self):
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def mapping(self):
        mapping = {}
        for row in self.records():
            alias = row["alias_id"]
            if row["action"] == "merge":
                mapping[alias] = row["canonical_id"]
            elif row["action"] == "revoke":
                mapping.pop(alias, None)
        return mapping

    def resolve(self, entity_id):
        mapping = self.mapping()
        seen = set()
        current = str(entity_id)
        while current in mapping:
            if current in seen:
                raise ValueError("Entity alias cycle")
            seen.add(current)
            current = mapping[current]
        return current

    def decide(self, alias_id, canonical_id, reviewer, action="merge"):
        alias_id, canonical_id = str(alias_id).strip(), str(canonical_id).strip()
        if action not in ("merge", "revoke") or not alias_id or not canonical_id or not reviewer:
            raise ValueError("Provide two IDs, reviewer and merge/revoke action")
        if alias_id == canonical_id:
            raise ValueError("Cannot alias an entity to itself")
        mapping = self.mapping()
        current = canonical_id
        while current in mapping:
            if current == alias_id:
                raise ValueError("Entity alias cycle")
            current = mapping[current]
        row = {"alias_id": alias_id, "canonical_id": canonical_id,
               "reviewer": str(reviewer), "action": action,
               "recorded_at": datetime.now(timezone.utc).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def apply(self, assertion):
        row = dict(assertion)
        for side in ("subject", "object"):
            key = side + "_id"
            if row.get(key):
                row[key] = self.resolve(row[key])
        return row

