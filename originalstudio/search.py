import time
from pathlib import Path

from .errors import StudioError
from .media import image_info
from .paths import generated_file
from .repository import like_pattern


def excerpt(text: str, query: str) -> str:
    terms = query.split()
    positions = [text.casefold().find(term.casefold()) for term in terms]
    matched = min((position for position in positions if position >= 0), default=0)
    start = max(0, matched - 75)
    end = min(len(text), start + 260)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


class SearchService:
    def __init__(self, repository, settings, engines):
        self.repository, self.db = repository, repository.db
        self.settings, self.engines = settings, engines

    def search(self, payload: dict):
        started = time.perf_counter()
        mode = payload["mode"]
        if mode == "filename":
            result = self.repository.assets({**payload, "q": payload.get("query") or payload.get("q", "")})
        elif mode in {"document", "dialogue"}:
            result = self.text_search(payload)
        else:
            result = self.visual_search(payload)
        result.update(mode=mode, elapsed_ms=round((time.perf_counter() - started) * 1000, 1))
        return result

    def text_search(self, payload):
        where, values = self.repository.filters(payload, include_query=False)
        terms = payload["query"].split()[:16]
        long_terms = [term for term in terms if len(term) >= 3]
        short_terms = [term for term in terms if len(term) < 3]
        kind = "document" if payload["mode"] == "document" else "transcript"
        conditions = [where, "a.available=1", "s.kind=?"]
        parameters = [*values, kind]
        if long_terms:
            source = "segment_fts JOIN segments s ON s.id=segment_fts.rowid JOIN assets a ON a.id=s.asset_id"
            conditions.append("segment_fts MATCH ?")
            parameters.append(" AND ".join('"' + term.replace('"', '""') + '"' for term in long_terms))
            ordering = "segment_fts.rank,s.id"
        else:
            source = "segments s JOIN assets a ON a.id=s.asset_id"
            ordering = "a.modified_at DESC,s.id"
        for term in short_terms:
            conditions.append("s.text LIKE ? ESCAPE '\\'")
            parameters.append(like_pattern(term))
        predicate = " AND ".join(conditions)
        page, size = payload["page"], payload["page_size"]
        with self.db.connect() as connection:
            total = connection.execute(f"SELECT COUNT(DISTINCT a.id) FROM {source} WHERE {predicate}", parameters).fetchone()[0]
            cursor = connection.execute(f"SELECT a.id,s.text,s.page,s.start,s.end FROM {source} WHERE {predicate} ORDER BY {ordering}", parameters)
            seen, matches = set(), []
            for row in cursor:
                if row["id"] in seen:
                    continue
                seen.add(row["id"])
                if len(seen) > (page - 1) * size:
                    matches.append(dict(row))
                if len(matches) == size:
                    break
            rows = [connection.execute("SELECT * FROM assets WHERE id=?", (match["id"],)).fetchone() for match in matches]
            items = self.repository.hydrate(connection, rows)
        for item, match in zip(items, matches):
            item["excerpt"] = excerpt(match["text"], payload["query"])
            item["location"] = {key: match[key] for key in ("page", "start", "end") if match[key] is not None}
        return {"items": items, "total": total, "page": page, "page_size": size}

    def visual_search(self, payload):
        engine = self.engines.vision
        if payload["mode"] == "reference":
            source = generated_file(self.db.directory / "references", f'{payload["reference_id"]}.jpg')
            _, image = image_info(source)
            query = engine.encode_image(image)
            if payload.get("query"):
                text_vector = engine.encode_text(payload["query"])
                blended = [0.75 * image_value + 0.25 * text_value for image_value, text_value in zip(query, text_vector)]
                length = max(sum(value * value for value in blended) ** 0.5, 1e-12)
                query = [value / length for value in blended]
        else:
            query = engine.encode_text(payload["query"])
        import numpy as np

        negative = engine.encode_text(payload["negative_query"]) if payload.get("negative_query") else None
        where, values = self.repository.filters(payload, include_query=False)
        best, frame_hits = {}, {}
        query_vector = np.asarray(query, dtype=np.float32)
        negative_vector = np.asarray(negative, dtype=np.float32) if negative else None
        with self.db.connect() as connection:
            cursor = connection.execute(f"SELECT e.asset_id,e.position,e.vector,a.duration FROM embeddings e JOIN assets a ON a.id=e.asset_id WHERE {where} AND a.available=1 AND a.visual_state='ready' AND e.model=? AND e.dimensions=?", [*values, engine.signature, len(query)])
            while batch := cursor.fetchmany(256):
                for row in batch:
                    vector = np.frombuffer(row["vector"], dtype=np.float32)
                    if vector.size != query_vector.size:
                        raise StudioError("视觉索引数据损坏，请重新建立视觉索引", "invalid_vector", 409)
                    score = float(np.dot(vector, query_vector)) * 100
                    if score < payload["min_score"]:
                        continue
                    if negative_vector is not None and float(np.dot(vector, negative_vector)) * 100 >= score:
                        continue
                    identifier = row["asset_id"]
                    if identifier not in best or score > best[identifier]["score"]:
                        best[identifier] = {"score": score, "position": row["position"], "duration": row["duration"]}
                    if row["position"] >= 0:
                        frame_hits.setdefault(identifier, []).append((row["position"], score))
            ranked = sorted(best, key=lambda identifier: (-best[identifier]["score"], identifier))
            page, size = payload["page"], payload["page_size"]
            selected = ranked[(page - 1) * size:page * size]
            rows = [connection.execute("SELECT * FROM assets WHERE id=?", (identifier,)).fetchone() for identifier in selected]
            items = self.repository.hydrate(connection, rows)
        for item in items:
            match = best[item["id"]]
            item["score"] = round(max(-100, min(100, match["score"])), 2)
            if item["kind"] == "video":
                step = max(self.settings.frame_interval, (match["duration"] or 0) / self.settings.max_video_frames)
                hits = sorted(position for position, score in frame_hits[item["id"]] if score >= match["score"] - 3)
                index = hits.index(match["position"])
                first = last = index
                while first > 0 and hits[first] - hits[first - 1] <= step * 2.1:
                    first -= 1
                while last + 1 < len(hits) and hits[last + 1] - hits[last] <= step * 2.1:
                    last += 1
                item["location"] = {"start": round(max(0, hits[first] - step / 2), 2), "end": round(min(match["duration"] or hits[last] + step, hits[last] + step / 2), 2)}
        return {"items": items, "total": len(ranked), "page": page, "page_size": size}
