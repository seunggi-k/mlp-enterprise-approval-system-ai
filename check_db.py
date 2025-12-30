import weaviate
from weaviate.connect import ConnectionParams

client = weaviate.WeaviateClient(
    connection_params=ConnectionParams.from_url("http://localhost:8080", grpc_port=50051)
)
client.connect()

try:
    collection = client.collections.get("ProvDocuments")
    # include_vector=True로 가져오면 v4에서는 딕셔너리 형태로 반환됩니다.
    response = collection.query.fetch_objects(limit=1, include_vector=True)
    
    if response.objects:
        obj = response.objects[0]
        print(f"📄 제목: {obj.properties['originalName']}")
        
        # Weaviate v4에서 벡터 꺼내기
        # obj.vector는 {'default': [0.1, 0.2, ...]} 형태입니다.
        vectors = obj.vector
        if "default" in vectors:
            actual_vector = vectors["default"]
            print(f"✅ 벡터 존재 여부: Yes")
            print(f"📏 실제 벡터 차원 수: {len(actual_vector)}") # 여기서 1024가 나와야 함!
        else:
            print("❌ 벡터 데이터가 'default' 키에 존재하지 않습니다.")
finally:
    client.close()