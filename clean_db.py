import weaviate
from weaviate.connect import ConnectionParams
import weaviate.classes.query as wvql

client = weaviate.WeaviateClient(
    connection_params=ConnectionParams.from_url("http://localhost:8080", grpc_port=50051)
)
client.connect()

try:
    collection = client.collections.get("TestDocs")
    
    # [수정] 모든 객체를 매칭해서 삭제하는 방식입니다.
    # 특정 조건 없이 모든 데이터를 지울 때 사용합니다.
    result = collection.data.delete_many(
        where=wvql.Filter.by_property("title").like("*")  # 모든 제목 매칭 (전체 삭제)
    )
    
    print(f"✅ 삭제 완료! 총 {result.failed == 0 and '모든' or '일부'} 데이터가 정리되었습니다.")
    print(f"📉 삭제된 데이터 수: {result.successful}")

finally:
    client.close()