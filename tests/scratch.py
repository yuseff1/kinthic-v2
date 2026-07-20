import asyncio
from silex_engine.storage.database import Database
from silex_engine.world.belief_engine import BeliefEngine
import time

async def run():
    db = Database(":memory:")
    await db.connect()
    be = BeliefEngine(db)
    
    await be.admit_evidence(claim="A", source_type="user", supports=True, confidence=0.9)
    await be.admit_evidence(claim="A", source_type="contradiction", supports=False, confidence=0.95)
    
    res = await db.fetch_all("SELECT * FROM evidence_ledger")
    for r in res:
        print("EVIDENCE:", dict(r))
        
    beliefs = await db.fetch_all("SELECT * FROM proposition_beliefs")
    for b in beliefs:
        print("BELIEF:", dict(b))
    
    await db.close()

if __name__ == "__main__":
    asyncio.run(run())
