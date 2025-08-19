from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import neura  # Import your assistant logic

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve HTML/CSS/JS files
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# Serve the main HTML page
@app.get("/", response_class=HTMLResponse)
async def serve_home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()
    
@app.post("/ask")
async def ask_neura(request: Request):
    data = await request.json()
    message = data.get("message", "")
    if not message:
        return {"error": "No message provided"}
    
    response = neura.ask_neura(message)
    return {"response": response}
