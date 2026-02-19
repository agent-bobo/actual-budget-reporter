
import os
import sys
from dotenv import load_dotenv
from actual import Actual
from actual.database import Transactions

# Load env vars
load_dotenv()

def main():
    url = os.getenv("ACTUAL_SERVER_URL")
    password = os.getenv("ACTUAL_PASSWORD")
    budget_id = os.getenv("ACTUAL_BUDGET_ID")
    
    print(f"Connecting to {url} with budget {budget_id}...")
    
    try:
        with Actual(
            base_url=url, 
            password=password, 
            file=budget_id, 
            encryption_password=None,
            cert=False 
        ) as actual:
            
            # Download budget (automatically handled if file is set, but explicit is fine too)
            print("✅ Connected and session established")
            
            # Query transactions
            print("Querying transactions...")
            # actual.session is a property that returns the session
            session = actual.session 
            txns = session.query(Transactions).limit(5).all()
            print(f"✅ Found {len(txns)} transactions (showing first 5):")
            for t in txns:
                # Transactions model might store amount in cents or int
                print(f"  - {t.date} {t.payee}: {t.amount}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
