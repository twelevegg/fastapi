
import sys
import os

# Add current directory to python path
sys.path.append(os.getcwd())

from app.core.config import settings
from qdrant_client import QdrantClient
import httpx

def test_connection(verify=True):
    print(f"\nTesting with verify={verify}...")
    try:
        # Note: qdrant-client documentation suggests verify is passed via **kwargs to the underlying client
        # but let's try passing it to QdrantClient constructor first.
        # If using gRPC it might be different, but URL suggests http/https.
        client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            # verify=verify # Passing verify directly to QdrantClient might work if it passes kwargs
        )
        
        # Manually injecting verify if constructor doesn't take it, but let's try straightforward first
        # It's better to pass it in constructor if supported
        
        # HACK: If constructor doesn't support it directly, we might need to patch it or pass it differently.
        # But let's check if the error persists first.
        
        # Actually, let's try to construct it with the specific argument
        # Based on library versions, it might be different.
        
        # We will try to instantiate with the verify kwarg
        client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            https=True,
            verify=verify
        )

        collections = client.get_collections()
        print(f"Success! Connection established. Found {len(collections.collections)} collections.")
        
        # Test specific collection access
        collection_name = settings.QDRANT_COLLECTION_NAME
        print(f"Checking collection '{collection_name}'...")
        client.get_collection(collection_name)
        print(f"Success! Collection '{collection_name}' verified.")

        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting SSL Test...")
    # Test 1: With verify=True (Default) - Expect Failure
    test_connection(verify=True)
    
    # Test 2: With verify=False - Expect Success
    test_connection(verify=False)
