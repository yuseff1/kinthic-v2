"""
silex_core/runtime/sandbox_runner.py — Phase 4 Code Self-Repair Sandbox & Mutation Engine

Implements safe subprocess execution (with resource limits and sanitized environments),
AST mutation operators, and soft fitness evaluation metrics.
"""

from __future__ import annotations

import ast
import asyncio
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

from silex_core.tools.system import _SAFE_HOST_ENV_PASSTHROUGH


class SandboxRunner:
    """Safely runs Python scripts inside a sanitized local subprocess environment."""

    def __init__(self, workspace_dir: Path | None = None):
        self.workspace_dir = workspace_dir or Path(os.getcwd())

    async def execute_python_code(
        self,
        code: str,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """
        Write code to a temporary file inside the workspace bounds,
        execute it under a sanitized environment with a timeout, and capture results.
        """
        # Create temp file
        temp_dir = self.workspace_dir / "scratch"
        os.makedirs(temp_dir, exist_ok=True)
        temp_file = temp_dir / f"sbx_{random.randint(1000, 9999)}.py"
        temp_file.write_text(code, encoding="utf-8")

        # Sanitize environment variables
        sanitized_env = {}
        for key in _SAFE_HOST_ENV_PASSTHROUGH:
            if key in os.environ:
                sanitized_env[key] = os.environ[key]

        # Exec python command in subprocess
        cmd = [sys.executable, str(temp_file)]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=sanitized_env,
                cwd=str(self.workspace_dir),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                exit_code = proc.returncode
                success = (exit_code == 0)
            except asyncio.TimeoutError:
                proc.kill()
                stdout, stderr = await proc.communicate()
                exit_code = -1
                success = False
                stderr = b"TimeoutError: Execution exceeded time limit."
        except Exception as e:
            exit_code = -2
            success = False
            stdout = b""
            stderr = str(e).encode("utf-8")
        finally:
            # Clean up temp file
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": exit_code,
            "success": success,
        }


# ------------------------------------------------------------------ #
#  AST Mutation Operators & Genetic Programming                       #
# ------------------------------------------------------------------ #

class ASTMutator(ast.NodeTransformer):
    """Mutates Python AST elements (constants, binary operators, compare operators)."""

    def __init__(self, mutation_rate: float = 0.5):
        self.mutation_rate = mutation_rate

    def visit_Constant(self, node: ast.Constant) -> Any:
        if random.random() < self.mutation_rate:
            if isinstance(node.value, (int, float)):
                # Mutate numbers by adding offset
                offset = random.choice([-2, -1, 1, 2])
                node.value += offset
            elif isinstance(node.value, str):
                # Mutate strings by appending suffix
                node.value += "_mut"
        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        if random.random() < self.mutation_rate:
            # Mutate arithmetic operators
            operators = [ast.Add, ast.Sub, ast.Mult, ast.Div]
            new_op = random.choice(operators)()
            node.op = new_op
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> Any:
        if random.random() < self.mutation_rate:
            # Mutate comparison operators (e.g. < to <=)
            ops = [ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE]
            node.ops = [random.choice(ops)()]
        return self.generic_visit(node)


def mutate_code(source: str, mutation_rate: float = 0.4) -> str:
    """Parse source to AST, apply random mutation, and unparse back to source."""
    try:
        tree = ast.parse(source)
        mutator = ASTMutator(mutation_rate)
        mutated_tree = mutator.visit(tree)
        ast.fix_missing_locations(mutated_tree)
        return ast.unparse(mutated_tree)
    except Exception:
        # If AST parsing/unparsing fails, return original
        return source


# ------------------------------------------------------------------ #
#  Soft Fitness Evaluation                                            #
# ------------------------------------------------------------------ #

def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def evaluate_fitness(
    original_code: str,
    variant_code: str,
    test_success: bool,
    complexity_weight: float = 0.05,
    distance_weight: float = 0.1,
) -> float:
    """
    Computes soft fitness:
    Fitness = 1.0 (if tests passed) - complexity_penalty - edit_distance_penalty
    """
    # 1. Base Score
    base_score = 1.0 if test_success else 0.0

    # 2. Complexity penalty (AST node count proxy)
    try:
        nodes_orig = len(list(ast.walk(ast.parse(original_code))))
        nodes_var = len(list(ast.walk(ast.parse(variant_code))))
        complexity_diff = max(0, nodes_var - nodes_orig)
        complexity_penalty = complexity_diff * complexity_weight
    except Exception:
        complexity_penalty = 0.0

    # 3. Parsimony distance penalty
    # Penalize large edits to preserve semantic proximity
    dist = levenshtein_distance(original_code, variant_code)
    max_len = max(len(original_code), 1)
    distance_penalty = (dist / max_len) * distance_weight

    return max(0.0, base_score - complexity_penalty - distance_penalty)
