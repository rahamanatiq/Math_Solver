import os
import sys
import django
import chromadb
import google.generativeai as genai

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_system.settings')
django.setup()

from django.conf import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

def get_document_context(query, k=3):
    db_dir = os.path.join(settings.BASE_DIR, 'db', 'chromadb_data')
    if not os.path.exists(db_dir):
        return "No documents found in knowledge base."
        
    client = chromadb.PersistentClient(path=db_dir)
    try:
        collection = client.get_collection(name="documents")
    except ValueError:
        return "No document index found. You may need to run ingestion."
        
    try:
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=query,
            task_type="retrieval_query"
        )
        query_embedding = result['embedding']
        
        fetch_k = max(k * 3, 20)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_k
        )
        
        if results and results['documents'] and results['documents'][0]:
            import random
            context_chunks = results['documents'][0]
            if len(context_chunks) > k:
                context_chunks = random.sample(context_chunks, k)
            return "\n\n---\n\n".join(context_chunks)
        
        return "No relevant context found in documents."
    except Exception as e:
        return f"Error retrieving context: {str(e)}"
