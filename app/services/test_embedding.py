from sentence_transformers import SentenceTransformer

sentences = ["안녕하세요?", "한국어 문장 임베딩을 위한 버트 모델입니다."]

model = SentenceTransformer("BAAI/bge-m3")
embeddings = model.encode(
    sentences,
    normalize_embeddings=True,   # ✅ 코사인 검색에 유리
)
print("shape:", embeddings.shape, "dtype:", embeddings.dtype)
first_preview = embeddings[0][:8].tolist()
print("first vector (8 dims):", first_preview)
