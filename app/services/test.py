import weaviate
from weaviate.connect import ConnectionParams

client = weaviate.WeaviateClient(
    connection_params=ConnectionParams.from_url("http://localhost:8080")  # 로컬에서 돌리면 localhost
)
client.connect()

print(client.get_meta())  # {"version": "..."} 등 출력되면 연결 OK

client.close()