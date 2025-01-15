from fastapi import FastAPI, UploadFile, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uvicorn
from pyngrok import ngrok
import os
from dotenv import load_dotenv
from meeting_transcriber import AudioTranscriber
import io
from contextlib import redirect_stdout

# Load environment variables
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Create upload directory if it doesn't exist
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Initialize transcriber
transcriber = AudioTranscriber(
    api_key=os.getenv('OPENAI_API_KEY'),
    language="es"
)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "transcript": None}
    )

@app.post("/transcribe", response_class=HTMLResponse)
async def transcribe(request: Request, audio: UploadFile):
    try:
        # Save uploaded file
        file_path = UPLOAD_DIR / audio.filename
        with open(file_path, "wb") as buffer:
            content = await audio.read()
            buffer.write(content)
        
        # Process the file
        f = io.StringIO()
        with redirect_stdout(f):
            if file_path.suffix.lower() == '.txt':
                with open(file_path, 'r', encoding='utf-8') as txt_file:
                    transcript = transcriber.enhance_transcript(txt_file.read())
            else:
                transcript = transcriber.transcribe_audio(str(file_path))
        
        # Extract cost information
        cost_info = ""
        for line in f.getvalue().split('\n'):
            if any(s in line.lower() for s in ['token usage', 'tokens:', 'cost:', '$']):
                cost_info += line + "<br>"
        
        # Clean up
        file_path.unlink()
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "transcript": transcript,
                "processing_status": "Procesamiento completado",
                "cost_info": cost_info
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "transcript": None,
                "processing_status": f"Error: {str(e)}",
                "cost_info": None
            }
        )

def start_server():
    # Start ngrok tunnel
    ngrok_tunnel = ngrok.connect(8000)
    print(f"Public URL: {ngrok_tunnel.public_url}")
    
    # Start uvicorn server
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    start_server() 