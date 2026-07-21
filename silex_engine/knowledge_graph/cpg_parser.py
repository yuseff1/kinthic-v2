"""
Code Property Graph (CPG) Parser (Phase 1)

Parses Python source files using tree-sitter to build a unified
Abstract Syntax Tree (AST), Control Flow Graph (CFG), and Program Dependence Graph (PDG / Reaching Defs)
and persists them into SQLite cpg_nodes and cpg_edges tables.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tree_sitter_languages
from silex_engine.logger import setup_logger
from silex_engine.storage.database import Database

log = setup_logger("kinthic.world_model.cpg_parser")


class DiffGraph:
    """In-memory staging area for CPG mutations to optimize transaction batching."""

    def __init__(self):
        self.nodes: list[dict] = []
        self.edges: list[dict] = []

    def add_node(
        self,
        label: str,
        code: str | None = None,
        line_number: int | None = None,
        column_number: int | None = None,
        file_temp_id: int | None = None,
        properties: dict | None = None,
    ) -> dict:
        node = {
            "label": label,
            "code": code,
            "line_number": line_number,
            "column_number": column_number,
            "file_temp_id": file_temp_id,
            "properties": properties or {},
            "db_id": None,
        }
        self.nodes.append(node)
        return node

    def add_edge(
        self,
        source: dict | int,
        target: dict | int,
        edge_type: str,
        property_val: str | None = None,
    ) -> None:
        self.edges.append(
            {
                "source": source,
                "target": target,
                "type": edge_type,
                "property": property_val,
            }
        )

    async def flush(self, db: Database) -> None:
        """Write all staged nodes and edges into SQLite in a single transaction."""
        now = datetime.now(timezone.utc).isoformat()
        async with db.transaction():
            # 1. Write nodes and capture database IDs
            for node in self.nodes:
                file_db_id = None
                if node["file_temp_id"] is not None:
                    # If file_temp_id is a dictionary representing another node
                    if isinstance(node["file_temp_id"], dict):
                        file_db_id = node["file_temp_id"]["db_id"]
                    else:
                        file_db_id = node["file_temp_id"]

                cursor = await db.execute(
                    """
                    INSERT INTO cpg_nodes (label, code, line_number, column_number, file_id, properties)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node["label"],
                        node["code"],
                        node["line_number"],
                        node["column_number"],
                        file_db_id,
                        json.dumps(node["properties"]),
                    ),
                )
                node["db_id"] = cursor.lastrowid

            # 2. Write edges
            edge_params = []
            for edge in self.edges:
                src = edge["source"]
                tgt = edge["target"]

                source_id = src["db_id"] if isinstance(src, dict) else src
                target_id = tgt["db_id"] if isinstance(tgt, dict) else tgt

                if source_id is None or target_id is None:
                    log.warning(f"Skipping edge due to unmapped database ID: {edge}")
                    continue

                edge_params.append(
                    (
                        source_id,
                        target_id,
                        edge["type"],
                        edge["property"],
                        now,
                        now,
                    )
                )

            if edge_params:
                await db.executemany(
                    """
                    INSERT OR REPLACE INTO cpg_edges (source_id, target_id, type, property, valid_from, valid_until, recorded_at)
                    VALUES (?, ?, ?, ?, ?, NULL, ?)
                    """,
                    edge_params,
                )


class CPGParser:
    """Parses source files into relational AST, CFG, and Reaching Definition structures."""

    def __init__(self, db: Database):
        self.db = db
        self.parser = tree_sitter_languages.get_parser("python")

    async def parse_file(self, filepath: Path) -> dict:
        """Parse a Python source file, construct CPG representation, and flush to SQLite."""
        if not filepath.exists():
            return {"error": f"File does not exist: {filepath}"}

        try:
            content = filepath.read_text(encoding="utf-8")
            tree = self.parser.parse(bytes(content, "utf-8"))
            root = tree.root_node

            diff = DiffGraph()

            # Create primary FILE node
            file_node = diff.add_node(
                label="FILE",
                code=str(filepath.relative_to(filepath.cwd()) if filepath.is_relative_to(filepath.cwd()) else filepath),
                line_number=1,
                column_number=1,
                properties={"filename": filepath.name, "absolute_path": str(filepath.resolve())},
            )

            # Traverse the AST to build nodes & edges
            self._walk_ast(root, file_node, file_node, diff, content)

            # Flush to SQLite inside single transaction
            await diff.flush(self.db)

            return {
                "status": "success",
                "nodes_count": len(diff.nodes),
                "edges_count": len(diff.edges),
            }

        except Exception as e:
            log.error(f"Error parsing file {filepath} to CPG: {e}", exc_info=True)
            return {"error": str(e)}

    def _walk_ast(
        self,
        node,
        parent_cpg_node: dict,
        file_node: dict,
        diff: DiffGraph,
        content: str,
    ) -> None:
        """Recursive AST walker extracting structures and nesting relationships."""
        label = node.type
        node_text = content[node.start_byte : node.end_byte]

        # Handle class and function scope nodes
        if label == "class_definition":
            name_node = node.child_by_field_name("name")
            class_name = content[name_node.start_byte : name_node.end_byte] if name_node else "AnonymousClass"
            cpg_node = diff.add_node(
                label="CLASS",
                code=node_text,
                line_number=node.start_point[0] + 1,
                column_number=node.start_point[1] + 1,
                file_temp_id=file_node,
                properties={"name": class_name},
            )
            diff.add_edge(parent_cpg_node, cpg_node, "AST")

            # Traverse body
            body_node = node.child_by_field_name("body")
            if body_node:
                self._walk_ast(body_node, cpg_node, file_node, diff, content)
            return

        elif label == "function_definition":
            name_node = node.child_by_field_name("name")
            func_name = content[name_node.start_byte : name_node.end_byte] if name_node else "anonymous"
            cpg_node = diff.add_node(
                label="METHOD",
                code=node_text,
                line_number=node.start_point[0] + 1,
                column_number=node.start_point[1] + 1,
                file_temp_id=file_node,
                properties={"name": func_name, "signature": f"{func_name}()"},
            )
            diff.add_edge(parent_cpg_node, cpg_node, "AST")

            # Parse parameters
            params_node = node.child_by_field_name("parameters")
            if params_node:
                # Walk parameters and create input nodes
                for param in params_node.named_children:
                    param_text = content[param.start_byte : param.end_byte]
                    param_node = diff.add_node(
                        label="METHOD_PARAMETER_IN",
                        code=param_text,
                        line_number=param.start_point[0] + 1,
                        column_number=param.start_point[1] + 1,
                        file_temp_id=file_node,
                        properties={"name": param_text},
                    )
                    diff.add_edge(cpg_node, param_node, "AST")

            # Parse body statements for local CFG & Reaching Defs
            body_node = node.child_by_field_name("body")
            if body_node:
                self._parse_method_body(body_node, cpg_node, file_node, diff, content)
            return

        # Fallback recursive traversal for other scopes
        for child in node.named_children:
            self._walk_ast(child, parent_cpg_node, file_node, diff, content)

    def _parse_method_body(
        self,
        body_node,
        method_cpg_node: dict,
        file_node: dict,
        diff: DiffGraph,
        content: str,
    ) -> None:
        """Parses a method's block of statements to construct intra-procedural AST, CFG, and data flow."""
        # 1. Collect all execution statements inside the method block recursively
        statements = []

        def collect_statements(n):
            stmt_types = {
                "expression_statement",
                "assignment",
                "return_statement",
                "if_statement",
                "while_statement",
                "for_statement",
                "raise_statement",
            }
            if n.type in stmt_types:
                statements.append(n)
            else:
                for child in n.named_children:
                    collect_statements(child)

        collect_statements(body_node)

        # Map each statement node to its corresponding created CPG statement node
        cpg_stmts = []
        for stmt in statements:
            stmt_text = content[stmt.start_byte : stmt.end_byte]
            
            # Unpack expression statements to find actual statement type
            underlying_type = stmt.type
            if stmt.type == "expression_statement" and stmt.named_child_count > 0:
                underlying_type = stmt.named_children[0].type

            # Categorize the node label
            lbl = "AST_NODE"
            if underlying_type == "assignment":
                lbl = "ASSIGN"
            elif stmt.type == "return_statement":
                lbl = "RETURN"
            elif underlying_type == "call" or "call" in stmt_text:
                lbl = "CALL"

            stmt_cpg = diff.add_node(
                label=lbl,
                code=stmt_text,
                line_number=stmt.start_point[0] + 1,
                column_number=stmt.start_point[1] + 1,
                file_temp_id=file_node,
                properties={"statement_type": stmt.type, "underlying_type": underlying_type},
            )
            diff.add_edge(method_cpg_node, stmt_cpg, "AST")
            cpg_stmts.append((stmt, stmt_cpg))

        # 2. Build local Control Flow Graph (CFG) edges sequentially
        for i in range(len(cpg_stmts) - 1):
            _, curr_cpg = cpg_stmts[i]
            _, next_cpg = cpg_stmts[i + 1]
            diff.add_edge(curr_cpg, next_cpg, "CFG")

        # 3. Simple local Reaching Definitions (data dependency) analysis
        # Track where variables are assigned (written) and where they are read.
        defs: dict[str, list[dict]] = {}  # var_name -> list of CPG statement nodes that define it

        for stmt, cpg_node in cpg_stmts:
            written_vars = self._extract_written_variables(stmt, content)
            read_vars = self._extract_read_variables(stmt, content)

            # Draw REACHING_DEF edges from the most recent definitions to this read
            for var in read_vars:
                if var in defs:
                    for prev_def in defs[var]:
                        diff.add_edge(prev_def, cpg_node, "REACHING_DEF", property_val=var)

            # Update active definitions list
            for var in written_vars:
                # Local override: clear previous definition references in this linear track
                defs[var] = [cpg_node]

    def _extract_written_variables(self, node, content: str) -> list[str]:
        """Extract variables being defined/written to in the given statement node."""
        written = []
        target = node
        if node.type == "expression_statement" and node.named_child_count > 0:
            if node.named_children[0].type == "assignment":
                target = node.named_children[0]

        if target.type == "assignment":
            left = target.child_by_field_name("left")
            if left:
                # Simple identifier assignment
                if left.type == "identifier":
                    written.append(content[left.start_byte : left.end_byte])
                elif left.type == "pattern_list" or left.type == "tuple":
                    # Tuple unpacking: x, y = ...
                    for child in left.named_children:
                        if child.type == "identifier":
                            written.append(content[child.start_byte : child.end_byte])
        return written

    def _extract_read_variables(self, node, content: str) -> list[str]:
        """Extract variables being read/referenced in the given statement node."""
        read = []

        def walk_reads(n, is_write_context=False):
            if n.type == "identifier":
                if not is_write_context:
                    read.append(content[n.start_byte : n.end_byte])
            elif n.type == "assignment":
                left = n.child_by_field_name("left")
                right = n.child_by_field_name("right")
                if left:
                    walk_reads(left, is_write_context=True)
                if right:
                    walk_reads(right, is_write_context=False)
            else:
                for child in n.named_children:
                    walk_reads(child, is_write_context)

        walk_reads(node)
        return list(set(read))
