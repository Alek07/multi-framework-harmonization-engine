"""UCM-13 - The embedding model: multilingual e5-base, on CPU, deterministic.

Three decisions here are load-bearing, and two of them are about being honest
regarding *how* reproducible this is.

**Why e5, and why the prefixes.** The catalog is written in Spanish
(`paraphrased_description`) while control titles are the frameworks' own English
(`Risk management objectives are established`), so the query and the passage it
must match are routinely in different languages. `intfloat/multilingual-e5-base`
is trained for exactly that, and it is trained *with* the `query:` / `passage:`
prefixes below — dropping them is not a stylistic choice, it measurably degrades
the retrieval, so `encode_query` and `encode_passages` are separate entry points
and neither takes raw text.

**Why CPU, and why one thread.** No GPU is assumed anywhere in this POC
(invariant 3: a foreign 8-16 GB machine must reproduce the result), so the device
is pinned to CPU rather than left to autodetect — a machine that happened to have
CUDA would otherwise produce different last bits than the one the TFM was
evaluated on. The thread count is pinned for the same reason one step down: a
multi-threaded reduction sums partial results in whatever order the threads
finish, which is not fixed between runs.

**What that does and does not guarantee.** With `EMBEDDING_NUM_THREADS=1` the
vectors are bit-identical run to run on the same machine, and that is what the
tests check. Across machines they are not: different CPUs take different SIMD
paths through the same matmul. What is stable across machines is the *ranking*
these vectors produce, which is what retrieval actually consumes — and 69
controls encoded once at index time is cheap enough that pinning one thread costs
nothing worth measuring. Claiming bit-exactness across machines here would be the
kind of unchecked claim the rest of this project refuses to make.
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

# The texts fed to the model are an input of the result, exactly like the parse
# prompt (UCM-12): changing how a control or a capability is rendered changes what
# is retrieved. So it is versioned, and the version travels in the provenance and
# in the collection's own name.
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

    Loading is lazy — the model is ~1.1 GB and is downloaded on first use, and the
    API must be able to come up on a machine that is still fetching it (the same
    reasoning as the Ollama digest check in UCM-12) — but lazy is *when*, not
    *whether*: the startup task warms it (`CatalogIndex.warm`) so the cost is not
    paid inside an operator's request.

    The cached model is loaded **offline first**. A load that is allowed to reach
    the Hub does so on every start even when the weights are already on disk,
    which costs a round-trip on the critical path and, worse, makes a cold start
    behave differently with and without network — not something a project whose
    third invariant is reproducibility should leave to chance. The networked load
    remains as the fallback, which is what the first run on a fresh machine
    needs.
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
