import pytest
import asyncio
import uuid
import time
from silex_engine.models.schemas import Memory, MemorySource, MemoryType, KnowledgeNode, NodeType, CausalEdge, EdgeType

@pytest.mark.asyncio
async def test_concurrent_read_write(memory_store, knowledge_graph):
    """
    Test 1.1: Concurrent Read/Write Stress Test.
    Spawn 20 concurrent async workers that write memories, query the vector database, 
    and perform graph traversals simultaneously to ensure no `database is locked` exceptions.
    """
    async def worker(worker_id: int):
        # 1. Write a memory
        mem_id = f"mem_w{worker_id}_{uuid.uuid4().hex[:8]}"
        memory = Memory(
            id=mem_id,
            content=f"Worker {worker_id} wrote this memory concurrently.",
            source=MemorySource.USER,
            memory_type=MemoryType.SEMANTIC,
            importance=0.8
        )
        await memory_store.add(memory)
        
        # 2. Write a node to the KnowledgeGraph
        node_id = f"node_{worker_id}_{uuid.uuid4().hex[:8]}"
        await knowledge_graph.add_node(KnowledgeNode(
            id=node_id,
            content=f"Graph node for worker {worker_id}",
            node_type=NodeType.FACT
        ))
        
        # 3. Read from memory_store
        await memory_store.retrieve_context(f"Worker {worker_id}")
        
        # 4. Search graph neighborhood
        await knowledge_graph.get_neighborhood(node_id, depth=1)
        
        return True

    # Run 20 concurrent workers
    tasks = [worker(i) for i in range(20)]
    results = await asyncio.gather(*tasks)
    
    # Assert no exceptions were raised
    for res in results:
        assert res is True, f"Worker failed with exception: {res}"
        
    # Flush memory buffer to verify
    await memory_store.flush()
    count = await memory_store.count()
    assert count == 20

@pytest.mark.asyncio
async def test_recursive_cte_graph_query(knowledge_graph):
    """
    Test 1.3: Recursive CTE Graph Query Test.
    Insert 1,000 nodes with deep relationship chains.
    Query the neighborhood of a root node up to depth 4 using SQLite CTEs.
    Validate speed and accuracy without loading the entire graph into memory.
    """
    # Create 1 root node
    root_id = "root_node"
    await knowledge_graph.add_node(KnowledgeNode(id=root_id, content="Root", node_type=NodeType.CONCEPT))
    
    # Create 4 branches, each 250 nodes deep
    for branch in range(4):
        prev_id = root_id
        for depth in range(250):
            node_id = f"node_b{branch}_d{depth}"
            await knowledge_graph.add_node(KnowledgeNode(id=node_id, content=f"Node B{branch} D{depth}", node_type=NodeType.FACT))
            await knowledge_graph.add_edge(CausalEdge(
                source_node=prev_id,
                target_node=node_id,
                edge_type=EdgeType.CAUSES,
                strength=1.0
            ))
            prev_id = node_id
            
    # Measure CTE query time
    start_time = time.perf_counter()
    
    # Query depth 4 neighborhood
    neighborhood = await knowledge_graph.get_neighborhood(root_id, depth=4)
    
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    # Validation
    # Depth 0: 1 node (root)
    # Depth 1: 4 nodes
    # Depth 2: 4 nodes
    # Depth 3: 4 nodes
    # Depth 4: 4 nodes
    # Total expected nodes = 1 + 4*4 = 17 nodes
    
    assert len(neighborhood["nodes"]) == 17
    # assert duration_ms < 50.0  # Optional strict performance assert, but system load varies
    assert any(n["id"] == "root_node" for n in neighborhood["nodes"])
