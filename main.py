import os
import shutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from rag_engine import ingest_file, load_db
from agent import run_agent

app = FastAPI(title="Agentic RAG Chatbot")

# Create required folders
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Mount the static files directory (for CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_ui():
    """Serves the front-end chat interface."""
    index_path = os.path.join("static", "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("Frontend files are still being created. Please wait...", status_code=503)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """API Endpoint to upload knowledge files (.txt, .md, .pdf)."""
    # Validate extension
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".txt", ".md", ".pdf"]:
        raise HTTPException(status_code=400, detail="Only .txt, .md, and .pdf files are supported.")
        
    filepath = os.path.join(UPLOAD_DIR, filename)
    try:
        # Save file to uploads folder
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Ingest file into vector database
        message = ingest_file(filepath)
        return {"status": "success", "message": message}
    except Exception as e:
        # Cleanup file if writing failed
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

@app.get("/files")
async def get_uploaded_files():
    """Returns a list of all unique documents currently stored in the database."""
    try:
        db = load_db()
        # Find unique sources in the DB JSON
        unique_sources = list(set(chunk.get("source") for chunk in db if "source" in chunk))
        return {"files": unique_sources}
    except Exception as e:
        return {"files": []}

@app.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """WebSocket endpoint for bi-directional live agent interaction and response streaming."""
    await websocket.accept()
    print("[WebSocket] Client connected.")
    
    try:
        while True:
            # Receive prompt from front-end
            data = await websocket.receive_json()
            user_query = data.get("query", "")
            chat_history = data.get("history", [])
            model_name = data.get("model", "llama3")  # Default to llama3 or qwen2.5-coder
            
            if not user_query:
                continue
                
            print(f"[WebSocket] User Query: {user_query} | Model: {model_name}")
            
            # Run our ReAct Agent loop, sending tokens and statuses via WebSocket
            await run_agent(user_query, chat_history, websocket, model_name=model_name)
            
            # Send close signal for this response
            await websocket.send_json({"type": "done"})
            
    except WebSocketDisconnect:
        print("[WebSocket] Client disconnected.")
    except Exception as e:
        print(f"[WebSocket] Error: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "content": f"WebSocket server error: {str(e)}"})
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)