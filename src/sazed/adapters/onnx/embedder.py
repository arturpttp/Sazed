"""multilingual-e5-small on onnxruntime (CPU). Mean pooling over the attention mask, then L2.

e5 expects a prefix. Commands and examples are compared symmetrically, so both sides use
"query: " (the e5 recommendation for non-retrieval similarity). Apply it here only.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import onnxruntime as ort
from tokenizers import Tokenizer

QUERY_PREFIX = "query: "


class OnnxEmbedder:
    def __init__(self, model_dir: Path, *, max_length: int = 128, threads: int = 0) -> None:
        tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=max_length)
        pad_id = tokenizer.token_to_id("<pad>")
        tokenizer.enable_padding(pad_id=pad_id, pad_token="<pad>")
        self._tokenizer = tokenizer
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self._session.get_inputs()}
        self._dim = int(self._run(["dimensão"]).shape[1])

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        # One sentence per run: the int8 model quantizes activations dynamically over the
        # whole batch, so a row's vector would depend on its batch-mates. Running each text
        # alone makes seed, learned and query vectors directly comparable.
        return np.vstack([self._run([text]) for text in texts])

    def _run(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        encodings = self._tokenizer.encode_batch([QUERY_PREFIX + t for t in texts])
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self._session.run(None, feed)[0]
        weights = mask[..., np.newaxis].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        pooled /= np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled.astype(np.float32)
