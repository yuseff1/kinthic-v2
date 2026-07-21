import pytest
from unittest.mock import MagicMock
from silex_engine.memory.raptor_tree import RAPTORTreeBuilder, RAPTORNode
from silex_core.tools.hybrid_retriever import HybridRetriever
from silex_engine.models.schemas import KnowledgeNode, NodeType

@pytest.mark.asyncio
async def test_raptor_tree_generation(db):
    # 1. Ingest distinct memories
    memories = [
        "React handles virtual DOM diffing",
        "React supports functional components",
        "Vue is a progressive JS framework",
        "Vue uses a template-based syntax",
        "Svelte compiles code to native JS",
        "Svelte has no virtual DOM overhead",
        "Docker isolates application runtimes",
        "Docker volumes persist container data"
    ]
    for i, content in enumerate(memories):
        await db.execute(
            """INSERT INTO memories (id, content, last_accessed, created_at, confidence, access_count)
               VALUES (?, ?, '2026-07-21T00:00:00Z', '2026-07-21T00:00:00Z', 0.8, 1)""",
            (f"base_mem_{i}", content)
        )

    # 2. Build RAPTOR Tree
    builder = RAPTORTreeBuilder(db)
    nodes = await builder.build_tree_from_memories(max_levels=2, cluster_size=3)

    # Base level 0 nodes + Level 1 summaries should be created
    assert len(nodes) > 8
    
    levels = {n.level for n in nodes}
    assert 0 in levels
    assert 1 in levels

    # 3. Verify nodes are saved in database
    db_nodes = await db.fetch_all("SELECT * FROM raptor_nodes")
    assert len(db_nodes) == len(nodes)


@pytest.mark.asyncio
async def test_hybrid_retriever_rrf_fusion(db):
    # 1. Seed memories for sparse search match
    await db.execute(
        """INSERT INTO memories (id, content, last_accessed, created_at, confidence, access_count)
           VALUES ('sparse_m1', 'React components render HTML elements', '2026-07-21T00:00:00', '2026-07-21T00:00:00', 0.9, 1)"""
    )
    # Seed knowledge graph node
    await db.execute(
        """INSERT INTO knowledge_nodes (id, content, node_type, confidence, source, created_at, last_validated)
           VALUES ('graph_m1', 'React handles virtual DOM', 'fact', 0.9, 'test', '2026-07-21T00:00:00', '2026-07-21T00:00:00')"""
    )

    # 2. Setup VectorStore mock to return a dense match
    vs_mock = MagicMock()
    vs_mock.is_active = True
    vs_mock.search = MagicMock(return_value=[
        {
            "id": "dense_m1",
            "content": "React applications run fast using direct bundle builds",
            "distance": 0.1
        }
    ])

    # 3. Retrieve
    retriever = HybridRetriever(db, vector_store=vs_mock)
    results = await retriever.retrieve_hybrid(query="React", top_n=5)

    # We should have matches from multiple channels fused
    assert len(results) > 0
    
    # Assert they have an rrf_score property
    assert "rrf_score" in results[0]
    
    # Assert descending RRF scores order
    scores = [r["rrf_score"] for r in results]
    assert scores == sorted(scores, reverse=True)
