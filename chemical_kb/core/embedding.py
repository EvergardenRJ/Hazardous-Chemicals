#封装Embedding
from sentence_transformers import SentenceTransformer

from core.config import EMBED_MODEL



class EmbeddingModel:


    def __init__(self):

        print(
            "加载BGE-M3"
        )


        self.model=SentenceTransformer(
            EMBED_MODEL,
            device="cuda"
        )



    def encode(
        self,
        text
    ):

        vector=self.model.encode(
            [text],
            normalize_embeddings=True
        )


        return vector.astype(
            "float32"
        )