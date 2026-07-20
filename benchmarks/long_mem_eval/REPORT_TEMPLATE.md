# LongMemEval Benchmark Report

**Dataset**: `longmemeval_s_cleaned.json`
**Total Questions**: 500
**Model**: gemini-2.5-flash (Placeholder)

## Overall Score
- **Total Correct**: [XX] / 500
- **Accuracy**: [XX]%

## Scores by Dimension

| Dimension | Questions | Correct | Accuracy |
| :--- | :--- | :--- | :--- |
| Information Extraction (IE) | [X] | [X] | [X]% |
| Multi-Session Reasoning (MR) | [X] | [X] | [X]% |
| Temporal Reasoning (TR) | [X] | [X] | [X]% |
| Knowledge Update (KU) | [X] | [X] | [X]% |
| Abstention (ABS) | [X] | [X] | [X]% |

## Methodology
The benchmark operates by evaluating the KINTHIC Silex Engine's retrieval capabilities on isolated multi-turn chat sessions. 
For each question:
1. Silex memory store is wiped clean.
2. The `haystack_sessions` belonging to the specific question are fully ingested using the `MemoryStore` API.
3. The benchmark queries the memory store (`silex_search`/`silex_recall`).
4. The retrieved memories are passed as context to an LLM alongside the test question.
5. A secondary LLM call acts as a judge, determining if the generated answer is semantically equivalent to the ground truth.

## Notes
- To run this benchmark, ensure `GEMINI_API_KEY` is exported in your environment or present in your `.env` file at the repository root.
- Command: `python run_benchmark.py --dataset longmemeval_s_cleaned.json`
