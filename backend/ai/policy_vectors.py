"""Persist local policy embeddings in Chroma and query only the active index."""

import json
import logging
import math
import os
from dataclasses import asdict
from hashlib import sha256
from threading import Lock
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from backend.storage.local_database import local_data_directory
from backend.ai.policy_retrieval import PolicyPassage


class VectorSearchError(Exception):
    """The local semantic index or embedding model is unavailable."""


def _ollama(path, payload=None):
    request = Request(
        f"http://127.0.0.1:11434/api/{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=120) as response:
            return json.load(response)
    except HTTPError as error:
        if path == "embed" and error.code == 400:
            raise VectorSearchError(
                "Ollama rejected a policy passage. It may exceed the model's input length. "
                "You can continue using keyword search."
            ) from error
        raise VectorSearchError(f"Ollama returned HTTP {error.code}. Check the local model service.") from error
    except (OSError, ValueError) as error:
        raise VectorSearchError("Check that Ollama is running and the embedding model is installed.") from error


def embedding_model():
    return os.environ.get("CLAIMS_EMBEDDING_MODEL", "embeddinggemma").strip() or "embeddinggemma"


def _model_digest(model):
    try:
        for entry in _ollama("tags")["models"]:
            if entry["name"] in {model, f"{model}:latest"}:
                return entry["digest"]
    except (KeyError, TypeError) as error:
        raise VectorSearchError("Could not verify the installed embedding model.") from error
    raise VectorSearchError(f"Install the local embedding model with: ollama pull {model}")


def embed_texts(texts, model, *, query=False):
    if model.split(":")[0] == "embeddinggemma":
        prefix = "task: search result | query: " if query else "title: Insurance policy | text: "
        texts = [prefix + text for text in texts]
    try:
        vectors = _ollama("embed", {
            "model": model, "input": texts, "truncate": False, "keep_alive": "1m",
        })["embeddings"]
        if len(vectors) != len(texts) or not vectors:
            raise ValueError
        dimensions = len(vectors[0])
        if dimensions == 0 or any(
            len(vector) != dimensions
            or not all(isinstance(value, (float, int)) and math.isfinite(value) for value in vector)
            or not any(vector)
            for vector in vectors
        ):
            raise ValueError
        return vectors
    except (KeyError, TypeError, ValueError) as error:
        raise VectorSearchError("The embedding service returned invalid vectors.") from error


_CLIENTS = {}
_BUILD_LOCK = Lock()
_LOG = logging.getLogger("uvicorn.error")


def _client(directory):
    if directory in _CLIENTS:
        return _CLIENTS[directory]
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as error:
        raise VectorSearchError("Install the project requirements to enable Chroma vector search.") from error
    client = chromadb.PersistentClient(
        path=directory, settings=Settings(anonymized_telemetry=False),
    )
    _CLIENTS[directory] = client
    return client


def _close_clients():
    """Close cached Chroma clients, mainly for isolated test data directories."""
    for client in _CLIENTS.values():
        client.close()
    _CLIENTS.clear()


def _collection(client, name):
    """Create the collection with its distance metric fixed at creation."""
    return client.get_or_create_collection(
        name, embedding_function=None, metadata={"hnsw:space": "cosine"},
    )


def _index_details(passages, customer_id=None):
    policy = [passage for passage in passages if not passage.recorded_estimate]
    if not policy:
        raise VectorSearchError("The uploaded policy has no readable passages to index.")
    model = embedding_model()
    digest = _model_digest(model)
    payload = json.dumps({
        "version": 1, "model": model, "digest": digest, "customer_id": customer_id,
        "passages": [{key: value for key, value in asdict(passage).items() if key != "hospital_document"}
                     for passage in policy],
    }, sort_keys=True)
    name = "policy_" + sha256(payload.encode()).hexdigest()[:48]
    client = _client(str(local_data_directory() / "policy_vectors"))
    return client, name, policy, model, digest


def index_status(passages, *, customer_id=None):
    try:
        client, name, policy, _, _ = _index_details(passages, customer_id)
        try:
            collection = client.get_collection(name, embedding_function=None)
        except Exception:
            return False
        return (collection.metadata or {}).get("ready") is True and collection.count() == len(policy)
    except VectorSearchError:
        raise
    except Exception as error:
        raise VectorSearchError("Could not open the local policy vector index.") from error


def build_vector_index(passages, *, customer_id=None):
    with _BUILD_LOCK:
        return _build_vector_index(passages, customer_id)


def _build_vector_index(passages, customer_id):
    stage = "opening local Chroma storage"
    try:
        client, name, policy, model, digest = _index_details(passages, customer_id)
        stage = "opening the policy collection"
        collection = _collection(client, name)
        if (collection.metadata or {}).get("ready") is True and collection.count() == len(policy):
            return len(policy)
        for offset in range(0, len(policy), 16):
            batch = policy[offset:offset + 16]
            ids = [str(index) for index in range(offset, offset + len(batch))]
            stage = "checking saved passages"
            existing = set(collection.get(ids=ids, include=[])["ids"])
            pending = [(key, passage) for key, passage in zip(ids, batch, strict=True) if key not in existing]
            if not pending:
                continue
            stage = "embedding policy passages"
            vectors = embed_texts([f"{p.search_context}\n{p.text}" for _, p in pending], model)
            stage = "saving policy passages in Chroma"
            collection.upsert(
                ids=[key for key, _ in pending],
                documents=[passage.text for _, passage in pending],
                embeddings=vectors,
                metadatas=[{"passage": json.dumps(asdict(passage)), "model_digest": digest} for _, passage in pending],
            )
        stage = "finalizing the policy index"
        if collection.count() != len(policy):
            raise VectorSearchError("The vector index is incomplete. Build it again to resume.")
        collection.modify(metadata={
            **{key: value for key, value in (collection.metadata or {}).items() if key != "hnsw:space"},
            "ready": True, "model": model, "model_digest": digest,
        })
        return len(policy)
    except VectorSearchError:
        raise
    except Exception as error:
        _LOG.warning("Policy index failed while %s (%s)", stage, type(error).__name__)
        raise VectorSearchError(
            f"Semantic indexing stopped while {stage} ({type(error).__name__}). "
            "You can retry the build or continue using keyword search."
        ) from error


def search_vectors(question, passages, limit=5, *, customer_id=None):
    """Retrieve only after the full active document and model index is ready."""
    try:
        client, name, policy, model, _ = _index_details(passages, customer_id)
        collection = client.get_collection(name, embedding_function=None)
        if (collection.metadata or {}).get("ready") is not True or collection.count() != len(policy):
            raise VectorSearchError("Build the semantic policy index before using vector search.")
        result = collection.query(
            query_embeddings=embed_texts([question], model, query=True),
            n_results=min(limit, len(policy)),
            include=["metadatas", "distances"],
        )
        return [
            PolicyPassage(**json.loads(metadata["passage"]))
            for metadata, distance in zip(result["metadatas"][0], result["distances"][0], strict=True)
            if distance <= 0.65
        ]
    except VectorSearchError:
        raise
    except Exception as error:
        raise VectorSearchError("The local semantic search failed. Rebuild the index or use keyword search.") from error
