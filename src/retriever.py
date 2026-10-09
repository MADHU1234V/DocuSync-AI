"""User-scoped similarity retrieval with stable source metadata."""

from src.config import get_settings
from src.ingestion import _collection, _embedding_model


def retrieve(user_id: str, question: str) -> list[dict]:
    collection = _collection(user_id)
    if collection.count() == 0:
        return []
    vector = _embedding_model().embed_query(question)
    results = collection.query(
        query_embeddings=[vector],
        n_results=get_settings().retrieval_k,
        where={"user_id": user_id},
        include=["documents", "metadatas", "distances"],
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    return [{"text": text, "metadata": metadata or {}, "distance": distance}
            for text, metadata, distance in zip(docs, metas, distances)]
