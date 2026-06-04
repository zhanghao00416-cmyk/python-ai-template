from __future__ import annotations

from qdrant_client import models

from app.schemas.vector_store import PayloadIndexConfig


_DISTANCE_MAP: dict[str, models.Distance] = {
    "Cosine": models.Distance.COSINE,
    "cosine": models.Distance.COSINE,
    "Euclid": models.Distance.EUCLID,
    "euclid": models.Distance.EUCLID,
    "Dot": models.Distance.DOT,
    "dot": models.Distance.DOT,
}


def get_distance(distance_str: str) -> models.Distance:
    return _DISTANCE_MAP.get(distance_str, models.Distance.COSINE)


def build_query_filter(
    payload_filters: dict[str, list[str]] | None,
) -> models.Filter | None:
    if not payload_filters:
        return None
    must_conditions: list[models.FieldCondition] = []
    for key, values in payload_filters.items():
        if not values:
            continue
        if len(values) == 1:
            match: models.MatchValue | models.MatchAny = models.MatchValue(
                value=values[0]
            )
        else:
            match = models.MatchAny(any=values)
        must_conditions.append(models.FieldCondition(key=key, match=match))
    if not must_conditions:
        return None
    return models.Filter(must=must_conditions)


def build_payload_index_params(
    indexes: list[PayloadIndexConfig],
) -> list[tuple[str, models.PayloadSchemaType | models.TextIndexParams]]:
    result: list[tuple[str, models.PayloadSchemaType | models.TextIndexParams]] = []
    for idx in indexes:
        if idx.type == "keyword":
            result.append((idx.field, models.PayloadSchemaType.KEYWORD))
        elif idx.type == "text":
            result.append(
                (
                    idx.field,
                    models.TextIndexParams(
                        type=models.TextIndexType.TEXT,
                        tokenizer=models.TokenizerType.WORD,
                        min_token_len=2,
                        max_token_len=20,
                    ),
                )
            )
        elif idx.type == "integer":
            result.append((idx.field, models.PayloadSchemaType.INTEGER))
        elif idx.type == "float":
            result.append((idx.field, models.PayloadSchemaType.FLOAT))
        elif idx.type == "bool":
            result.append((idx.field, models.PayloadSchemaType.BOOL))
        else:
            result.append((idx.field, models.PayloadSchemaType.KEYWORD))
    return result