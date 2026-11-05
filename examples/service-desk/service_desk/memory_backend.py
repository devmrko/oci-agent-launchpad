"""Application-owned pool and embedding configuration; no runtime schema creation."""

import asyncio
import json
import os
from pathlib import Path


def resources():
    import numpy as np
    import oci
    import oracledb
    from oracleagentmemory.apis.embedders import IEmbedder
    from python_foundation.agent_memory import OracleMemory, oracle_memory_client

    cfg = json.loads(Path(os.environ["DESK_MEMORY_CONFIG"]).read_text())
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(
        {},
        signer=oci.auth.signers.InstancePrincipalsSecurityTokenSigner(),
        service_endpoint="https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com",
        timeout=(5, 25),
        retry_strategy=oci.retry.NoneRetryStrategy(),
    )

    class Embeddings(IEmbedder):
        embedding_dimension = 1536
        max_input_tokens = 8192

        def embed(self, texts, *, is_query=False):
            from oci.generative_ai_inference.models import EmbedTextDetails, OnDemandServingMode

            response = client.embed_text(
                EmbedTextDetails(
                    compartment_id=cfg["compartment"],
                    serving_mode=OnDemandServingMode(model_id="cohere.embed-v4.0"),
                    inputs=texts,
                    input_type="SEARCH_QUERY" if is_query else "SEARCH_DOCUMENT",
                    truncate="NONE",
                )
            )
            vectors = np.asarray(response.data.embeddings, dtype=np.float32)
            if vectors.shape != (len(texts), 1536) or not np.isfinite(vectors).all():
                raise ValueError("Invalid embedding result")
            return vectors

        async def embed_async(self, texts, *, is_query=False):
            return await asyncio.to_thread(self.embed, texts, is_query=is_query)

    pool = oracledb.create_pool(
        user=cfg["user"],
        password=cfg["password"],
        dsn=cfg["dsn"],
        min=1,
        max=3,
        increment=1,
        tcp_connect_timeout=10,
        retry_count=0,
    )
    try:
        memory_client = oracle_memory_client(
            pool, Embeddings(), store_id="LPMEM", schema_owner="LP_MEMORY_OWNER"
        )
    except Exception:
        pool.close()
        raise
    return OracleMemory(memory_client, namespace="launchpad-service-desk"), pool, memory_client
