"""The embedding model: multilingual e5-base, on CPU, deterministic.

The catalog is Spanish while control titles are the frameworks' own English, so
query and passage are routinely cross-language: `intfloat/multilingual-e5-base` is
trained for that, *with* the `query:` / `passage:` prefixes below — dropping them
measurably degrades retrieval, so `encode_query`/`encode_passages` are separate and
neither takes raw text. CPU and a single thread are pinned for reproducibility
(invariant 3): a CUDA machine or a multi-threaded reduction would produce different
last bits. With `EMBEDDING_NUM_THREADS=1` the vectors are bit-identical run to run on
the same machine (what the tests check); across machines only the *ranking* is stable
— different CPUs take different SIMD paths — and claiming bit-exactness across machines
would be an unchecked claim.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from app.catalog.schemas import Capability, FrameworkControl
from app.core.config import settings
from app.core.exceptions import AppException

if TYPE_CHECKING:  # pragma: no cover - import cost is paid lazily at runtime
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# app/retrieval/embeddings.py -> parents[2] == backend root (server/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]

# The texts fed to the model are an input of the result, like the parse prompt:
# changing how a control or capability is rendered changes what is retrieved. So it
# is versioned, and the version travels in the provenance and the collection name.
TEXT_TEMPLATE_VERSION = "1.0.0"

# e5's asymmetric prefixes. The model was trained with them; they are not decoration.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


class EmbeddingUnavailableError(AppException):
    """The embedding model could not be loaded (not cached, and no network)."""

    status_code = 503


def capability_text(capability: Capability) -> str:
    """What a capability looks like as a query: the outcome, in the operator's words.

    The OT refinements are included because they are what distinguishes this
    catalog's reading of a capability from the generic one — "sin agente
    residente", "sin reinicio del proceso" — and they are precisely the words that
    should pull an OT mechanism ahead of an IT one.
    """
    parts = [capability.name, capability.description, *capability.ot_refinements]
    return ". ".join(part.strip().rstrip(".") for part in parts if part and part.strip()) + "."


def control_text(control: FrameworkControl) -> str:
    """What a control looks like as a passage.

    The framework and its official ID are left out on purpose. They are payload —
    filterable, exact, and already used for that — and putting them in the encoded
    text would let a query match on the *name of a standard* rather than on what
    the control does, which is the one thing this pass is supposed to look at.
    """
    return f"{control.title.strip().rstrip('.')}. {control.paraphrased_description.strip()}"


class Encoder:
    """Thin wrapper over the sentence-transformers model, with the e5 protocol applied."""

    def __init__(self, model: SentenceTransformer):
        self.model = model

    def encode_query(self, text: str) -> list[float]:
        return self._encode([f"{QUERY_PREFIX}{text}"])[0]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"{PASSAGE_PREFIX}{text}" for text in texts])

    def _encode(self, texts: list[str]) -> list[list[float]]:
        # Normalised vectors so Qdrant's cosine distance is a plain dot product and
        # the scores it reports are comparable between capabilities.
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in vectors]


@lru_cache(maxsize=1)
def get_encoder() -> Encoder:
    """Load the pinned model once per process, on CPU, with threads pinned.

    Loading is lazy (the ~1.1 GB model is fetched on first use, so the API can come
    up while it is still downloading), but the startup task warms it
    (`CatalogIndex.warm`) so the cost is not paid inside an operator's request. It is
    loaded offline first: a load allowed to reach the Hub round-trips on every start
    and makes a cold start behave differently with and without network (against
    invariant 3). The networked load is the fallback for a fresh machine's first run.
    """
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - the dependency is declared
        raise EmbeddingUnavailableError(
            f"Falta la dependencia de embeddings ({exc}). Ejecute `uv sync` en server/."
        ) from exc

    torch.set_num_threads(settings.EMBEDDING_NUM_THREADS)

    cache = Path(settings.EMBEDDING_CACHE_DIR)
    if not cache.is_absolute():
        cache = BACKEND_ROOT / cache

    def load(*, offline: bool) -> SentenceTransformer:
        return SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device="cpu",
            cache_folder=str(cache),
            local_files_only=offline,
        )

    try:
        model = load(offline=True)
        logger.info("Embeddings: %s cargado desde la caché local", settings.EMBEDDING_MODEL)
    except Exception:
        try:
            model = load(offline=False)
            logger.info(
                "Embeddings: %s descargado (primer uso); las siguientes cargas son locales",
                settings.EMBEDDING_MODEL,
            )
        except Exception as exc:
            raise EmbeddingUnavailableError(
                f"No se pudo cargar el modelo de embeddings '{settings.EMBEDDING_MODEL}': {exc}. "
                "En el primer arranque necesita red para descargarlo (~1,1 GB); después se sirve "
                f"desde la caché en {cache}."
            ) from exc

    dimension = model.get_embedding_dimension()
    if dimension != settings.EMBEDDING_DIM:
        raise EmbeddingUnavailableError(
            f"El modelo '{settings.EMBEDDING_MODEL}' produce vectores de {dimension} "
            f"dimensiones, no las {settings.EMBEDDING_DIM} fijadas. La colección de Qdrant se "
            "crea con la dimensión configurada: con esta discrepancia no se puede indexar."
        )

    return Encoder(model)
