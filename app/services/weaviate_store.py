from functools import lru_cache
from typing import List

import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.connect import ConnectionParams

from app.core.config import settings


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
