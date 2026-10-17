"""Dense embedders behind one interface.

- "lsa": TF-IDF + truncated SVD fitted on the corpus. Offline, free, sovereign; a weak but
  honest dense baseline that runs anywhere (including CI without keys).
- "mistral": `mistral-embed` through the provider-agnostic client (needs MISTRAL_API_KEY).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def _normalise(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(norms, 1e-12)


class LSAEmbedder:
    """Latent semantic analysis: TF-IDF (word 1-2-grams) projected to `dim` dimensions with a
    truncated SVD fitted on the corpus. Stored as plain arrays (no pickle):
    lsa-vocab.json, lsa-idf.npy, lsa-components.npy (vocab × dim, float32)."""

    name = "lsa"

    def __init__(self, root: Path, dim: int = 256, max_features: int = 100_000,
                 seed: int = 42) -> None:
        self.root = Path(root)
        self.dim, self.max_features, self.seed = dim, max_features, seed
        self.vectorizer = None
        self.components: np.ndarray | None = None

    def _vectorizer(self, vocabulary=None, min_df=1):
        from sklearn.feature_extraction.text import TfidfVectorizer

        from filing_assistant.text import tokenize
        return TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False,
                               sublinear_tf=True, min_df=min_df, ngram_range=(1, 2),
                               max_features=None if vocabulary else self.max_features,
                               vocabulary=vocabulary)

    def fit(self, texts: list[str]) -> LSAEmbedder:
        import json

        from sklearn.decomposition import TruncatedSVD

        self.vectorizer = self._vectorizer(min_df=2 if len(texts) > 50 else 1)
        x = self.vectorizer.fit_transform(texts)
        dim = max(2, min(self.dim, x.shape[1] - 1, len(texts) - 1))
        svd = TruncatedSVD(n_components=dim, random_state=self.seed).fit(x)
        self.components = svd.components_.T.astype(np.float32)
        vocab = sorted(self.vectorizer.vocabulary_, key=self.vectorizer.vocabulary_.get)
        (self.root / "lsa-vocab.json").write_text(json.dumps(vocab))
        np.save(self.root / "lsa-idf.npy", self.vectorizer.idf_.astype(np.float32))
        np.save(self.root / "lsa-components.npy", self.components)
        return self

    def _ensure(self) -> None:
        if self.vectorizer is None:
            import json
            vocab = json.loads((self.root / "lsa-vocab.json").read_text())
            self.vectorizer = self._vectorizer(vocabulary={t: i for i, t in enumerate(vocab)})
            self.vectorizer.idf_ = np.load(self.root / "lsa-idf.npy")
            self.components = np.load(self.root / "lsa-components.npy")

    def embed_documents(self, texts: list[str]) -> tuple[np.ndarray, dict]:
        self._ensure()
        return _normalise(np.asarray(self.vectorizer.transform(texts) @ self.components)), {}

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0][0]

    def describe(self) -> dict:
        return {"kind": "lsa", "dim": int(self.components.shape[1]) if self.components is not None
                else self.dim, "vocabulary": int(self.components.shape[0])
                if self.components is not None else None}


class MistralEmbedder:
    name = "mistral"

    def __init__(self, client=None) -> None:
        from filing_assistant.llm import client_for
        self.client = client or client_for("mistral")

    def embed_documents(self, texts: list[str]) -> tuple[np.ndarray, dict]:
        vectors, usage = self.client.embed(texts, batch_size=32)
        return _normalise(np.array(vectors, dtype=np.float32)), usage

    def embed_query(self, text: str) -> np.ndarray:
        vectors, _ = self.client.embed([text])
        return _normalise(np.array(vectors, dtype=np.float32))[0]

    def describe(self) -> dict:
        return {"kind": "mistral", "model": self.client.provider.model_for("embed")}


def get_embedder(name: str, index_root: Path, fit_texts: list[str] | None = None):
    if name == "lsa":
        emb = LSAEmbedder(Path(index_root))
        if fit_texts is not None:
            emb.fit(fit_texts)
        return emb
    if name == "mistral":
        return MistralEmbedder()
    raise ValueError(f"unknown embedder {name!r}; use lsa or mistral")
