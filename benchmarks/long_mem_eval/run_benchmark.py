import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from tqdm import tqdm
from google import genai
from pydantic import BaseModel
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

# Ensure silex_engine is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from silex_engine.storage.database import Database
from silex_engine.world.graph import KnowledgeGraph
from silex_engine.memory.memory_store import MemoryStore

class BenchmarkResult(BaseModel):
    question_id: str
    question_type: str
    predicted: str
    ground_truth: str
    score: int  # 0 or 1
    reasoning: str

async def clear_memory(db: Database, memory: MemoryStore):
    """Wipes the database and vector store between evaluation episodes."""
    if memory.vs.is_active:
        memory.vs.clear()
    await db._db.execute("DELETE FROM memories")
    await db._db.commit()

async def ingest_sessions(memory: MemoryStore, sessions: list):
    """Ingests a conversational history into the memory store."""
    for turn in sessions:
        role = turn.get("role", "unknown")
        content = turn.get("content", "")
        formatted_content = f"{role.capitalize()}: {content}"
        
        # Add to semantic memory
        await memory.add_manual(
            content=formatted_content,
            importance=0.6,
            tags=["longmemeval", role]
        )

async def evaluate_question(client, memory: MemoryStore, question_data: dict) -> BenchmarkResult:
    question = question_data["question"]
    ground_truth = question_data["answer"]
    
    # Retrieval
    retrieved_memories = await memory.search(question, limit=10)
    context_str = "\n".join([f"- {m.content}" for m in retrieved_memories])
    
    # Prompt LLM
    prompt = f"""You are an AI assistant with access to a memory database.
Answer the following question based ONLY on the retrieved memories below.
Keep your answer concise.

RETRIEVED MEMORIES:
{context_str}

QUESTION:
{question}
"""
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    predicted = response.text.strip()
    
    # Scoring (simple string match or LLM-as-a-judge)
    # For simplicity, we use exact/partial match here. In a real eval, use an LLM-as-a-judge.
    score_prompt = f"""Compare the PREDICTED answer with the GROUND TRUTH answer.
Are they semantically equivalent or does the PREDICTED answer correctly satisfy the GROUND TRUTH?
Respond with exactly '1' for yes, and '0' for no.

GROUND TRUTH: {ground_truth}
PREDICTED: {predicted}
"""
    score_response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=score_prompt
    )
    score_val = 1 if '1' in score_response.text else 0
    
    return BenchmarkResult(
        question_id=str(question_data.get("question_id", "unknown")),
        question_type=question_data.get("question_type", "unknown"),
        predicted=predicted,
        ground_truth=ground_truth,
        score=score_val,
        reasoning=score_response.text
    )

async def main():
    parser = argparse.ArgumentParser(description="LongMemEval Benchmark")
    parser.add_argument("--limit", type=int, default=10, help="Number of questions to evaluate")
    parser.add_argument("--dataset", type=str, default="longmemeval_s_cleaned.json", help="Path to dataset JSON")
    args = parser.parse_args()

    # Isolate benchmark DB
    os.environ["SILEX_DB"] = "benchmark_silex.db"
    os.environ["SILEX_VECTOR_DB"] = "benchmark_vector.db"

    print(f"Loading dataset from {args.dataset}...")
    with open(args.dataset, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    # Initialize Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    # Initialize Silex
    db = Database(os.environ["SILEX_DB"])
    await db.connect()
    kg = KnowledgeGraph(db)
    await kg.load()
    memory = MemoryStore(db)

    dataset = dataset[:args.limit]
    results = []
    
    print(f"Starting evaluation of {len(dataset)} questions...")
    for idx, row in enumerate(tqdm(dataset, desc="Evaluating")):
        # 1. Clear memory
        await clear_memory(db, memory)
        
        # 2. Ingest
        sessions = row.get("haystack_sessions", [])
        await ingest_sessions(memory, sessions)
        
        # 3. Evaluate
        result = await evaluate_question(client, memory, row)
        results.append(result.model_dump())
        
    # Write report
    report_path = "REPORT.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    score = sum(r["score"] for r in results)
    print(f"\nEvaluation Complete!")
    print(f"Total Score: {score}/{len(results)} ({(score/len(results))*100:.2f}%)")
    print(f"Results saved to {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
