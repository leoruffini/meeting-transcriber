from fastapi import FastAPI, UploadFile, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path
import uvicorn
import os
from dotenv import load_dotenv
from meeting_transcriber import AudioTranscriber
import io
from contextlib import redirect_stdout
import logging

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

@app.get("/transcribe", response_class=HTMLResponse)
async def transcribe_get(request: Request):
    # Redirect to home page if someone tries to access /transcribe directly
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "transcript": None
        }
    )

@app.post("/transcribe", response_class=HTMLResponse)
async def transcribe(request: Request, audio: UploadFile):
    try:
        # Keep logging for debugging but don't show in UI
        log_buffer = io.StringIO()
        log_handler = logging.StreamHandler(log_buffer)
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger = logging.getLogger('meeting_transcriber')
        logger.addHandler(log_handler)
        
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
                    status_message = "✅ Text enhancement completed successfully"
            else:
                transcript = transcriber.transcribe_audio(str(file_path))
                status_message = "✅ Audio transcription completed successfully"
        
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
                "processing_status": status_message,  # Just the simple message
                "cost_info": cost_info
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "transcript": None,
                "processing_status": f"Error processing file: {str(e)}",
                "cost_info": None
            }
        )

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port) 