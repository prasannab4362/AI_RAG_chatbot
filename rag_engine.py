import os
import json
import re
import math
import numpy as np
import requests
from pypdf import PdfReader

# Database file to store ingested chunks
DB_FILE = "db.json"

# --- HELPER FUNCTIONS ---

def extract_text_from_pdf(filepath: str) -> str:
    """Extracts raw text from a PDF file."""
    text = ""
    try:
        reader = PdfReader(filepath)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    except Exception as e:
        print(f"Error reading PDF {filepath}: {e}")
    return text

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 150) -> list:
    """Splits text into chunks of character length with a specified overlap."""
    chunks = []
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += (chunk_size - overlap)
    return chunks

# --- OLLAMA EMBEDDINGS (VECTOR SEARCH) ---

def get_ollama_embedding(text: str, model_name: str = "nomic-embed-text") -> list:
    """Gets text embedding vector from Ollama."""
    url = "http://localhost:11434/api/embeddings"
    try:
        response = requests.post(
            url, 
            json={"model": model_name, "prompt": text}, 
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get("embedding")
    except Exception as e:
        # Fallback to general API if model not found
        pass
    return None

# --- PURE PYTHON KEYWORD SEARCH (FALLBACK / STUDY MATERIAL) ---

def tokenize(text: str) -> list:
    """Simple tokenizer that cleans and splits words."""
    return re.findall(r'\w+', text.lower())

def keyword_search(query: str, chunks: list, top_k: int = 3) -> list:
    """Performs a TF-IDF style keyword search across chunks in pure Python."""
    query_tokens = set(tokenize(query))
    if not query_tokens or not chunks:
        return []
        
    # 1. Calculate Document Frequency (DF)
    df = {}
    for chunk in chunks:
        tokens = set(tokenize(chunk["text"]))
        for t in tokens:
            df[t] = df.get(t, 0) + 1
            
    # 2. Score chunks based on TF-IDF
    scores = []
    N = len(chunks)
    for chunk in chunks:
        tokens = tokenize(chunk["text"])
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
            
        score = 0.0
        for token in query_tokens:
            if token in tf and token in df:
                # TF (Term Frequency) normalized by chunk length
                tf_val = tf[token] / len(tokens)
                # IDF (Inverse Document Frequency)
                idf = math.log((N + 1) / (df[token] + 0.5))
                score += tf_val * idf
        scores.append((score, chunk))
        
    # Sort by score descending and return top K
    scores.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scores[:top_k] if item[0] > 0]

# --- CORE RAG OPERATIONS ---

def load_db() -> list:
    """Loads chunks from the JSON database."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_db(chunks: list):
    """Saves chunks to the JSON database."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2)

def ingest_file(filepath: str, embedding_model: str = "nomic-embed-text") -> str:
    """Extracts text, chunks it, retrieves embeddings, and saves to database."""
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    
    # 1. Extract raw text
    if ext == ".pdf":
        text = extract_text_from_pdf(filepath)
    elif ext in [".txt", ".md"]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            return f"Error reading file {filename}: {str(e)}"
    else:
        return f"Unsupported file type: {ext}"
        
    if not text.strip():
        return f"No readable text found in {filename}."
        
    # 2. Chunk text
    chunks = chunk_text(text)
    db = load_db()
    
    # Remove existing chunks for this specific file to avoid duplication
    db = [c for c in db if c.get("source") != filename]
    
    # 3. Embed & store chunks
    new_chunks_count = 0
    for chunk in chunks:
        # Try to generate vector embedding
        embedding = get_ollama_embedding(chunk, embedding_model)
        
        db.append({
            "text": chunk,
            "source": filename,
            "embedding": embedding  # Can be list of floats or None
        })
        new_chunks_count += 1
        
    save_db(db)
    return f"Successfully ingested '{filename}'! Split into {new_chunks_count} chunks."

def query_documents(query: str, embedding_model: str = "nomic-embed-text") -> str:
    """Searches local database and returns relevant chunks as context."""
    db = load_db()
    if not db:
        return "No documents have been uploaded yet. Please upload files to search them."
        
    # 1. Attempt Vector Search
    query_vector = get_ollama_embedding(query, embedding_model)
    
    if query_vector is not None:
        # Filter chunks that actually have embeddings
        vector_chunks = [c for c in db if c.get("embedding") is not None]
        
        if vector_chunks:
            # Compute cosine similarity
            q_vec = np.array(query_vector)
            q_norm = np.linalg.norm(q_vec)
            
            similarities = []
            for chunk in vector_chunks:
                c_vec = np.array(chunk["embedding"])
                c_norm = np.linalg.norm(c_vec)
                
                if q_norm > 0 and c_norm > 0:
                    similarity = np.dot(q_vec, c_vec) / (q_norm * c_norm)
                else:
                    similarity = 0.0
                similarities.append((similarity, chunk))
                
            # Sort by similarity descending
            similarities.sort(key=lambda x: x[0], reverse=True)
            top_matches = [item[1] for item in similarities[:3] if item[0] > 0.1]
            
            if top_matches:
                context_str = ""
                for idx, chunk in enumerate(top_matches, 1):
                    context_str += f"[Source: {chunk['source']}]\n{chunk['text']}\n\n"
                return context_str

    # 2. Fallback to Keyword Search (if vector search fails or model does not support it)
    print("[RAG Engine] Falling back to Keyword Search...")
    keyword_matches = keyword_search(query, db, top_k=3)
    if keyword_matches:
        context_str = ""
        for idx, chunk in enumerate(keyword_matches, 1):
            context_str += f"[Source: {chunk['source']}]\n{chunk['text']}\n\n"
        return context_str
        
    return "No matching information found in the uploaded documents."