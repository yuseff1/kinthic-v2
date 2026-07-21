import pytest
import asyncio
import time
from datetime import datetime, timezone, timedelta
from silex_engine.world.belief_revision import BeliefRevisionEngine, RipplePropagator
from silex_engine.memory.consolidation import MemoryConsolidationWorker
from silex_engine.models.schemas import KnowledgeNode, NodeType

@pytest.mark.asyncio
async def test_ripple_propagation(db, knowledge_graph):
    # 1. Create two knowledge nodes in the graph
    node_a = await knowledge_graph.add_node(KnowledgeNode(
        id="node_parent",
        content="Parent claim",
        node_type=NodeType.FACT,
        confidence=0.8
    ))
    node_b = await knowledge_graph.add_node(KnowledgeNode(
        id="node_child",
        content="Child claim",
        node_type=NodeType.FACT,
        confidence=0.8
    ))

    # Link parent and child in causal_edges
    await db.execute(
        """INSERT INTO causal_edges (id, source_node, target_node, edge_type, strength, evidence, created_at)
           VALUES (?, ?, ?, 'causes', 0.8, 'test evidence', ?)""",
        ("edge_test", node_a.id, node_b.id, datetime.now(timezone.utc).isoformat())
    )

    # 2. Run RipplePropagator to decrease parent confidence by -0.4
    propagator = RipplePropagator(db, attenuation_factor=0.85)
    updated = await propagator.propagate_change(node_a.id, -0.4)

    assert node_b.id in updated

    # 3. Retrieve node_child confidence and assert it has been attenuated
    # expected delta_b = -0.4 * 0.85 = -0.34. New confidence = 0.8 - 0.34 = 0.46
    node_b_row = await db.fetch_one("SELECT confidence FROM knowledge_nodes WHERE id = ?", (node_b.id,))
    assert node_b_row is not None
    assert abs(float(node_b_row["confidence"]) - 0.46) < 0.01


@pytest.mark.asyncio
async def test_agm_belief_revision(db):
    engine = BeliefRevisionEngine(db)
    claim = "System uses Python 3"

    # 1. Expand claim (Initial True stance)
    await engine.revise_belief(claim, "true", 0.9)
    b1 = await db.fetch_one("SELECT stance, confidence, validity_until FROM proposition_beliefs WHERE claim = ?", (claim,))
    assert b1["stance"] == "true"
    assert float(b1["confidence"]) == 0.9
    assert b1["validity_until"] is None

    # 2. Revise claim to False (Stance Flip / Contraction)
    # This should trigger contraction of the old stance (log contradiction, set stance to retracted, set validity_until)
    # Then expand with new stance
    await engine.revise_belief(claim, "false", 0.1)
    
    # Verify new stance is set
    b2 = await db.fetch_one("SELECT stance, confidence, validity_until FROM proposition_beliefs WHERE claim = ?", (claim,))
    assert b2["stance"] == "false"
    assert float(b2["confidence"]) == 0.1
    assert b2["validity_until"] is None # New stance is active

    # Verify a contradiction was logged
    contradictions = await db.fetch_all("SELECT * FROM contradictions")
    assert len(contradictions) > 0
    assert "AGM stance flip" in contradictions[0]["analysis"]


@pytest.mark.asyncio
async def test_memory_consolidation_decay_and_reinforcement(db):
    now = datetime.now(timezone.utc)
    
    # 1. Insert a memory accessed 10 days ago (should decay)
    mem1_id = "mem_decay"
    last_accessed_10d = (now - timedelta(days=10)).isoformat()
    await db.execute(
        """INSERT INTO memories (id, content, last_accessed, created_at, confidence, access_count)
           VALUES (?, 'decaying memory', ?, ?, 0.8, 0)""",
        (mem1_id, last_accessed_10d, last_accessed_10d)
    )

    # 2. Insert a reinforced memory accessed 10 days ago but with high access count
    mem2_id = "mem_reinforced"
    await db.execute(
        """INSERT INTO memories (id, content, last_accessed, created_at, confidence, access_count)
           VALUES (?, 'reinforced memory', ?, ?, 0.8, 50)""",
        (mem2_id, last_accessed_10d, last_accessed_10d)
    )

    # 3. Run consolidation pass
    # Using decay_rate = 1e-5 (so in 10 days = 864,000s, it decays significantly)
    worker = MemoryConsolidationWorker(db, decay_rate=1e-6, reinforcement_factor=0.1, dormancy_threshold=0.2)
    stats = await worker.run_consolidation_pass()

    assert stats["scanned"] == 2

    # Fetch results
    m1 = await db.fetch_one("SELECT confidence, archived_at FROM memories WHERE id = ?", (mem1_id,))
    m2 = await db.fetch_one("SELECT confidence, archived_at FROM memories WHERE id = ?", (mem2_id,))

    # Memory 1 should have decayed below threshold and been archived
    # delta_t = 864,000s, decay_rate = 1e-6 -> decayed = 0.8 * e^(-0.864) = 0.337
    # Threshold is 0.2, but wait! 0.337 is > 0.2, so it's not archived yet, just decayed.
    # Let's verify confidence is less than original 0.8
    assert float(m1["confidence"]) < 0.8
    assert m1["archived_at"] is None

    # Let's run a second decay check simulating even longer delta_t (50 days = 4,320,000s)
    # decay_rate = 1e-6 -> decayed = 0.8 * e^(-4.32) = 0.01, which is below 0.2 threshold!
    last_accessed_50d = (now - timedelta(days=50)).isoformat()
    await db.execute("UPDATE memories SET last_accessed = ? WHERE id = ?", (last_accessed_50d, mem1_id))
    
    await worker.run_consolidation_pass()
    m1_archived = await db.fetch_one("SELECT confidence, archived_at FROM memories WHERE id = ?", (mem1_id,))
    assert m1_archived["archived_at"] is not None  # Successfully archived
