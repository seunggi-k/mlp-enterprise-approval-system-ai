from functools import lru_cache
from typing import List, Optional

import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter
from weaviate.connect import ConnectionParams

from app.core.config import settings
from app.services.provdocuments.embeddings import embed_chunks


COLLECTION_NAME = settings.WEAVIATE_COLLECTION


@lru_cache(maxsize=1)
def get_client() -> weaviate.WeaviateClient:
    if not settings.WEAVIATE_HTTP_URL:
        raise RuntimeError("WEAVIATE_HTTP_URL이 설정되지 않았습니다.")
    params = ConnectionParams.from_url(
        settings.WEAVIATE_HTTP_URL,
        grpc_port=settings.WEAVIATE_GRPC_PORT,
    )
    client = weaviate.WeaviateClient(connection_params=params)
    client.connect()
    return client


def ensure_collection(client: weaviate.WeaviateClient):
    existing = client.collections.list_all()
    if COLLECTION_NAME in existing:
        return
    client.collections.create(
        name=COLLECTION_NAME,
        vectorizer_config=Configure.Vectorizer.none(),
        properties=[
            Property(name="comId", data_type=DataType.TEXT),
            Property(name="provNo", data_type=DataType.INT),
            Property(name="objectKey", data_type=DataType.TEXT),
            Property(name="originalName", data_type=DataType.TEXT),
            Property(name="chunkIndex", data_type=DataType.INT),
            Property(name="content", data_type=DataType.TEXT),
        ],
    )


def store_prov_chunks(
    com_id: str,
    prov_no: int,
    object_key: str,
    original_name: str,
    chunks: List[str],
    embeddings,
):
    """
    Store each chunk embedding in Weaviate with company/prov metadata.
    """
    client = get_client()
    ensure_collection(client)
    coll = client.collections.get(COLLECTION_NAME)

    for idx, (chunk, vec) in enumerate(zip(chunks, embeddings)):
        coll.data.insert(
            properties={
                "comId": com_id,
                "provNo": prov_no,
                "objectKey": object_key,
                "originalName": original_name,
                "chunkIndex": idx,
                "content": chunk,
            },
            vector=vec.tolist(),
        )


def delete_prov_chunks(com_id: str, prov_no: int) -> int:
    """
    Delete all chunks for a company/provNo. Returns deleted count (best-effort).
    """
    client = get_client()
    ensure_collection(client)
    coll = client.collections.get(COLLECTION_NAME)
    where = Filter.all_of([
        Filter.by_property("comId").equal(com_id),
        Filter.by_property("provNo").equal(prov_no),
    ])
    res = coll.data.delete_many(where=where)
    try:
        deleted = res.results["successful"]  # type: ignore[dict-item]
        print(f"[WEAVIATE] delete comId={com_id} provNo={prov_no} deleted={deleted}")
        return deleted
    except Exception as e:
        print(f"[WEAVIATE] delete result parse failed: {e} raw={res}")
        return 0


def search_prov_chunks(
    query: str,
    top_k: int = 5,
    com_id: Optional[str] = None,
    prov_no: Optional[int] = None,
) -> List[str]:
    """
    Vector search over 규약 청크. Returns top chunks' content text.
    """
    client = get_client()
    ensure_collection(client)
    coll = client.collections.get(COLLECTION_NAME)

    query_vec = embed_chunks([query])[0].tolist()

    where_filters = []
    if com_id:
        where_filters.append(Filter.by_property("comId").equal(com_id))
    if prov_no is not None:
        where_filters.append(Filter.by_property("provNo").equal(prov_no))
    where = Filter.all_of(where_filters) if where_filters else None

    res = coll.query.near_vector(
        near_vector=query_vec,
        filters=where,
        limit=top_k,
        return_properties=["content", "originalName", "chunkIndex", "comId", "provNo"],
    )

    snippets: List[str] = []
    try:
        for obj in res.objects:  # type: ignore[attr-defined]
            props = obj.properties or {}
            content = props.get("content")
            if not content:
                continue
            origin = props.get("originalName") or props.get("comId")
            idx = props.get("chunkIndex")
            prefix_parts = [p for p in [origin, f"chunk#{idx}" if idx is not None else None] if p]
            prefix = " ".join(prefix_parts)
            snippet = f"{prefix} {content}".strip() if prefix else content
            snippets.append(snippet)
    except Exception as e:
        print(f"[WEAVIATE] search parse failed: {e} raw={res}")
        return []

    return snippets
