import pytest
from pathlib import Path
from silex_engine.knowledge_graph.cpg_parser import CPGParser
from silex_engine.world.graph import KnowledgeGraph

@pytest.mark.asyncio
async def test_cpg_parsing_and_traversal(db, tmp_path):
    # 1. Create a dummy Python file to parse
    test_code = """
def process_data(input_val):
    x = input_val
    y = x + 10
    return y
"""
    file_path = tmp_path / "dummy.py"
    file_path.write_text(test_code, encoding="utf-8")

    # 2. Run CPGParser
    parser = CPGParser(db)
    result = await parser.parse_file(file_path)

    assert result["status"] == "success"
    assert result["nodes_count"] > 0
    assert result["edges_count"] > 0

    # 3. Query the database to verify nodes are created
    nodes = await db.fetch_all("SELECT * FROM cpg_nodes")
    # Verify we have FILE, METHOD, METHOD_PARAMETER_IN, ASSIGN, and RETURN nodes
    labels = {n["label"] for n in nodes}
    assert "FILE" in labels
    assert "METHOD" in labels
    assert "METHOD_PARAMETER_IN" in labels
    assert "ASSIGN" in labels
    assert "RETURN" in labels

    # Find the parameter node and assignment nodes
    param_node = [n for n in nodes if n["label"] == "METHOD_PARAMETER_IN"][0]
    assign_nodes = [n for n in nodes if n["label"] == "ASSIGN"]
    assert len(assign_nodes) >= 2

    # 4. Check edges
    edges = await db.fetch_all("SELECT * FROM cpg_edges")
    edge_types = {e["type"] for e in edges}
    assert "AST" in edge_types
    assert "CFG" in edge_types
    assert "REACHING_DEF" in edge_types

    # Verify a reaching definition path exists from parameter to first assignment
    reaching_defs = [e for e in edges if e["type"] == "REACHING_DEF"]
    assert len(reaching_defs) > 0

    # 5. Test k-hop traversal query using KnowledgeGraph.find_cpg_flow_paths
    kg = KnowledgeGraph(db)
    
    # Let's find flow paths starting from the first assignment node
    first_assign_id = assign_nodes[0]["id"]
    flow_paths = await kg.find_cpg_flow_paths(first_assign_id, max_depth=5)
    
    # We should be able to reach subsequent statements (next ASSIGN, RETURN)
    assert len(flow_paths) > 0
    flow_labels = {f["label"] for f in flow_paths}
    assert "ASSIGN" in flow_labels
    assert "RETURN" in flow_labels

    # 6. Test file cleanup cascading
    await kg.clear_cpg_file(str(file_path.relative_to(file_path.cwd()) if file_path.is_relative_to(file_path.cwd()) else file_path))
    
    # Nodes and edges for that file should be completely removed
    remaining_nodes = await db.fetch_all("SELECT * FROM cpg_nodes")
    remaining_edges = await db.fetch_all("SELECT * FROM cpg_edges")
    assert len(remaining_nodes) == 0
    assert len(remaining_edges) == 0
