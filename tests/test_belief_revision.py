import pytest
import asyncio
from silex_engine.world.belief_engine import BeliefEngine
from silex_engine.world.contradictions import ContradictionDetector
from silex_engine.models.schemas import Contradiction, KnowledgeNode, NodeType

@pytest.mark.asyncio
async def test_causal_contradiction_detection(db, knowledge_graph):
    """
    Test 1.2: Causal Trait & Belief Revision Test
    Ingest a fact, then ingest a contradicting fact.
    Validate that the contradiction detector flags the conflict and updates the belief score of the old fact.
    """
    detector = ContradictionDetector(db, knowledge_graph)
    belief_engine = BeliefEngine(db)
    
    # 1. Admit evidence for the original claim
    claim_a = "User project is written in React"
    await belief_engine.admit_evidence(
        claim=claim_a,
        source_type="user_statement",
        supports=True,
        confidence=0.9
    )
    await asyncio.sleep(0.2)
    
    # Verify belief state for Claim A
    belief_a = await belief_engine.get_belief(claim_a)
    assert belief_a["stance"] == "true"
    assert belief_a["confidence"] > 0.8
    
    # 2. Add the nodes to the knowledge graph so the contradiction detector can find them
    node_a = await knowledge_graph.add_node(KnowledgeNode(
        id="node_a",
        content=claim_a,
        node_type=NodeType.FACT,
        confidence=0.9
    ))
    
    claim_b = "User migrated the project to Vue"
    node_b = await knowledge_graph.add_node(KnowledgeNode(
        id="node_b",
        content=claim_b,
        node_type=NodeType.FACT,
        confidence=0.9
    ))
    
    # 3. Process the contradiction where B overrides A (confidence > 0.6 means new claim wins)
    contradiction = Contradiction(
        existing_claim=claim_a,
        new_claim=claim_b,
        analysis="The user explicitly stated they migrated away from React to Vue.",
        confidence=0.95
    )
    
    stored_contradiction = await detector.process_contradiction(contradiction)
    await asyncio.sleep(0.2)
    
    assert stored_contradiction is not None
    assert stored_contradiction.status == "unresolved"
    
    # Verify the graph edge was created
    edges = await db.fetch_all("SELECT * FROM causal_edges WHERE source_node = ?", (node_a.id,))
    assert len(edges) > 0
    assert any(e["target_node"] == node_b.id and e["edge_type"] == "contradicts" for e in edges)
    
    # Verify that node A's confidence was downgraded
    updated_node_a = await db.fetch_one("SELECT confidence FROM knowledge_nodes WHERE id = ?", (node_a.id,))
    assert updated_node_a["confidence"] < 0.9  # Downgraded by 0.2
    
    # 4. Admit evidence for the new claim (Claim B) and negative evidence for Claim A
    await belief_engine.admit_evidence(claim=claim_b, source_type="user_statement", supports=True, confidence=0.95)
    await belief_engine.admit_evidence(claim=claim_a, source_type="contradiction", supports=False, confidence=0.95)
    await asyncio.sleep(0.2)
    
    # Validate final belief states
    final_belief_a = await belief_engine.get_belief(claim_a)
    final_belief_b = await belief_engine.get_belief(claim_b)
    
    assert final_belief_b["stance"] == "true"
    assert final_belief_a["stance"] in ["uncertain", "false"]
    assert final_belief_a["confidence"] < 0.5
