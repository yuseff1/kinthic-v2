import pytest
import asyncio
from pathlib import Path
from silex_core.runtime.sandbox_runner import SandboxRunner, mutate_code, evaluate_fitness
from silex_core.ops.gepa_optimizer import GEPAOptimizer, PromptCandidate

@pytest.mark.asyncio
async def test_sandbox_execution(tmp_path):
    runner = SandboxRunner(tmp_path)

    # 1. Test successful run
    res1 = await runner.execute_python_code('print("hello from sandbox")')
    assert res1["success"] is True
    assert "hello from sandbox" in res1["stdout"]

    # 2. Test syntax error run
    res2 = await runner.execute_python_code('x = [unclosed bracket')
    assert res2["success"] is False
    assert "SyntaxError" in res2["stderr"]

    # 3. Test timeout safety
    res3 = await runner.execute_python_code('import time\ntime.sleep(10)', timeout=1.0)
    assert res3["success"] is False
    assert "TimeoutError" in res3["stderr"]


def test_ast_mutation():
    code = "x = 10 + 5"
    mutated = mutate_code(code, mutation_rate=1.0)

    # Verify mutated code is valid python syntax but different from original constant/operator
    assert mutated != code
    # We can compile it to ensure it is valid Python
    compiled = compile(mutated, "<string>", "exec")
    assert compiled is not None


def test_soft_fitness_evaluation():
    orig = "def add(a, b):\n    return a + b"
    variant1 = "def add(a, b):\n    return a - b" # Minor mutation (distance penalty small)
    variant2 = "def add(a, b):\n    print('hello world')\n    return a + b" # Adds complexity

    # Evaluate fitness
    f1 = evaluate_fitness(orig, variant1, test_success=True)
    f2 = evaluate_fitness(orig, variant2, test_success=True)

    # Both tests succeeded, but variant2 has more nodes/lines (complexity penalty)
    assert f1 > 0.0
    assert f2 > 0.0


def test_gepa_pareto_frontier():
    # Candidates list:
    # A: length 50 words, accuracy 0.9 (Pareto Front)
    # B: length 30 words, accuracy 0.8 (Pareto Front - trade-off)
    # C: length 60 words, accuracy 0.8 (Dominated by A: more words, lower accuracy)
    # D: length 50 words, accuracy 0.85 (Dominated by A: same words, lower accuracy)
    a = PromptCandidate("A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A A", 0.9)
    b = PromptCandidate("B B B B B B B B B B B B B B B B B B B B B B B B B B B B B B", 0.8)
    c = PromptCandidate("C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C C", 0.8)
    d = PromptCandidate("D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D D", 0.85)

    optimizer = GEPAOptimizer("base prompt")
    front = optimizer.select_pareto_front([a, b, c, d])

    # Only A and B should be in the Pareto Front
    assert a in front
    assert b in front
    assert c not in front
    assert d not in front
