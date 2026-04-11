import os
import sys
import django
from pypdf import PdfReader
import docx
import chromadb
import google.generativeai as genai

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_system.settings')
django.setup()

from django.conf import settings
from chatbot.models import Document, DocumentChunk

genai.configure(api_key=settings.GEMINI_API_KEY)

def get_text_chunks(text, chunk_size=1000, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks

def ingest():
    docs_dir = os.path.join(settings.BASE_DIR, 'documents')
    os.makedirs(docs_dir, exist_ok=True)
    
    db_dir = os.path.join(settings.BASE_DIR, 'db', 'chromadb_data')
    os.makedirs(db_dir, exist_ok=True)
    
    client = chromadb.PersistentClient(path=db_dir)
    collection = client.get_or_create_collection(name="documents")
    
    found_any = False
    for filename in os.listdir(docs_dir):
        if filename.endswith('.pdf') or filename.endswith('.docx'):
            found_any = True
            file_path = os.path.join(docs_dir, filename)
            
            if Document.objects.filter(filename=filename).exists():
                print(f"Skipping {filename}, already ingested.")
                continue
            
            print(f"Processing {filename}...")
            text = ""
            if filename.endswith('.pdf'):
                reader = PdfReader(file_path)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            elif filename.endswith('.docx'):
                doc = docx.Document(file_path)
                for para in doc.paragraphs:
                    text += para.text + "\n"
                
            chunks = get_text_chunks(text)
            
            ids = []
            documents = []
            embeddings = []
            metadatas = []
            
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                try:
                    result = genai.embed_content(
                        model="models/gemini-embedding-001",
                        content=chunk,
                        task_type="retrieval_document"
                    )
                    embedding = result['embedding']
                    
                    ids.append(f"{filename}_{i}")
                    documents.append(chunk)
                    embeddings.append(embedding)
                    metadatas.append({"filename": filename, "chunk_index": i})
                except Exception as e:
                    print(f"Error embedding chunk {i} of {filename}: {e}")
            
            if ids:
                collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
            
            doc_obj = Document.objects.create(filename=filename)
            for i, chunk in enumerate(documents):
                DocumentChunk.objects.create(
                    document=doc_obj,
                    chunk_index=metadatas[i]["chunk_index"],
                    text=chunk
                )
            print(f"Successfully ingested {filename} and saved chunks to Admin.")
            
    if not found_any:
        print(f"No PDF or DOCX files found in {docs_dir}.")

if __name__ == '__main__':
    ingest()
