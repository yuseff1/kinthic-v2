import os
import shutil
import sys
from pathlib import Path

def main():
    print("=== KINTHIC DATABASE RESET UTILITY ===")
    
    # Paths relative to the codebase root (D:\varsen\kinthic)
    cwd = Path(os.getcwd())
    db_file = cwd / "silex.db"
    db_wal = cwd / "silex.db-wal"
    db_shm = cwd / "silex.db-shm"
    db_lock = cwd / "silex.db.lock"
    vector_db = cwd / "silex_vector.db"
    
    # Also check user home ~/.kinthic folder
    home_dir = Path.home() / ".kinthic"
    home_db = home_dir / "storage" / "silex.db"
    home_db_wal = home_dir / "storage" / "silex.db-wal"
    home_db_shm = home_dir / "storage" / "silex.db-shm"
    home_vector = home_dir / "storage" / "vector_db"
    
    print("\nTarget locations:")
    print(f"  Local workspace DB: {db_file} (exists: {db_file.exists()})")
    print(f"  Local vector DB: {vector_db} (exists: {vector_db.exists()})")
    print(f"  Home directory DB: {home_db} (exists: {home_db.exists()})")
    print(f"  Home vector DB: {home_vector} (exists: {home_vector.exists()})")
    
    # Check locks
    if db_lock.exists():
        try:
            with open(db_lock, "r") as f:
                pid = f.read().strip()
            print(f"\n⚠️  WARNING: Local database lock file exists. PID holding lock: {pid}")
            print("Please terminate any active uvicorn/kinthic daemon processes first (like Process 21408 in WSL).")
        except Exception:
            pass
            
    confirm = input("\nAre you sure you want to delete all memories and reset Kinthic databases? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Reset aborted.")
        sys.exit(0)
        
    print("\nDeletes in progress...")
    
    # Local files
    for f in [db_file, db_wal, db_shm, db_lock]:
        if f.exists():
            try:
                os.remove(f)
                print(f"  Removed {f.name}")
            except Exception as e:
                print(f"  [ERROR] Could not remove {f.name}: {e}")
                
    if vector_db.exists():
        try:
            shutil.rmtree(vector_db)
            print("  Removed silex_vector.db directory")
        except Exception as e:
            print(f"  [ERROR] Could not remove silex_vector.db: {e}")
            
    # Home files
    for f in [home_db, home_db_wal, home_db_shm]:
        if f.exists():
            try:
                os.remove(f)
                print(f"  Removed Home {f.name}")
            except Exception as e:
                print(f"  [ERROR] Could not remove Home {f.name}: {e}")
                
    if home_vector.exists():
        try:
            shutil.rmtree(home_vector)
            print("  Removed Home vector_db directory")
        except Exception as e:
            print(f"  [ERROR] Could not remove Home vector_db: {e}")
            
    print("\n✓ Reset complete. A fresh, empty database will be created next time you start Kinthic v2.")

if __name__ == "__main__":
    main()
