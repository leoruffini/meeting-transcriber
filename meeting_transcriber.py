from openai import OpenAI
from pathlib import Path
import time
from dotenv import load_dotenv
import os
from pydub import AudioSegment
import math
from prompts import TRANSCRIPT_ENHANCEMENT_PROMPT
import sys
import logging

# Configure logging after the imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class AudioTranscriber:
    def __init__(self, api_key, model="gpt-4o", language="es"):
        self.client = OpenAI(api_key=api_key)
        self.language = language
        self.model = model  # Add model as class attribute
        
        # Print selected configuration
        print(f"Initialized with:")
        print(f"- Model: {self.model}")
        print(f"- Language: {self.language}")

    def get_audio_duration(self, audio_path):
        """Get duration of audio file"""
        audio = AudioSegment.from_file(audio_path)
        duration = len(audio) / 1000  # Convert milliseconds to seconds
        print(f"Audio duration: {duration:.2f} seconds")
        return duration

    def split_audio(self, audio_path, max_size_mb=15):
        """Split audio file if it's larger than max_size_mb"""
        logger.info(f"Checking if audio file needs splitting (max size: {max_size_mb}MB)")
        file_size = Path(audio_path).stat().st_size / (1024 * 1024)  # Size in MB
        
        if file_size <= max_size_mb:
            logger.info("Audio file is within size limits, no splitting needed")
            return [audio_path]
            
        logger.info(f"Audio file is {file_size:.2f}MB, splitting into chunks...")
        audio = AudioSegment.from_file(audio_path)
        duration_ms = len(audio)
        
        # Calculate number of chunks needed
        chunk_duration = math.floor(duration_ms * (max_size_mb / file_size))
        # Add a 10% safety margin to chunk duration
        chunk_duration = int(chunk_duration * 0.90)  # Increased safety margin
        num_chunks = math.ceil(duration_ms / chunk_duration)
        
        chunks = []
        for i in range(num_chunks):
            logger.info(f"Processing chunk {i+1}/{num_chunks}")
            start = i * chunk_duration
            end = min((i + 1) * chunk_duration, duration_ms)
            chunk_path = f"{Path(audio_path).stem}_chunk{i}.wav"
            # Export with lower quality to reduce file size
            audio[start:end].export(
                chunk_path, 
                format="wav",
                parameters=["-ac", "1", "-ar", "16000"]  # Mono audio, 16kHz
            )
            chunks.append(chunk_path)
            logger.info(f"Successfully created chunk {i+1}/{num_chunks}")
            
        return chunks

    def enhance_transcript(self, raw_transcript):
        """Enhance transcript readability and structure using the configured model"""
        try:
            logger.info("Starting transcript enhancement process")
            logger.info(f"Using model: {self.model}")
            
            print("Mejorando transcripción...")
            
            messages = [
                {
                    "role": "user",
                    "content": TRANSCRIPT_ENHANCEMENT_PROMPT + "\n\nTRANSCRIPCION:\n" + raw_transcript
                }
            ]
            
            logger.info("Sending request to OpenAI for enhancement")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            
            logger.info("Successfully received enhanced transcript")
            
            enhanced_transcript = response.choices[0].message.content
            
            # Print detailed token usage and costs
            if hasattr(response, 'usage'):
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                total_tokens = response.usage.total_tokens
                
                # Calculate costs based on model
                if self.model == "gpt-4o":
                    input_cost = (input_tokens / 1_000_000) * 15.00
                    output_cost = (output_tokens / 1_000_000) * 60.00
                else:
                    input_cost = (input_tokens / 1_000_000) * 2.50
                    output_cost = (output_tokens / 1_000_000) * 10.00
                
                total_cost = input_cost + output_cost
                
                print("\nToken usage and cost details:")
                print(f"Input tokens: {input_tokens:,} (${input_cost:.4f})")
                print(f"Output tokens: {output_tokens:,} (${output_cost:.4f})")
                print(f"Total tokens: {total_tokens:,}")
                print(f"Total cost: ${total_cost:.4f}")
            
            return enhanced_transcript
            
        except Exception as e:
            logger.error(f"Error during transcript enhancement: {str(e)}")
            return raw_transcript

    def transcribe_audio(self, audio_path):
        """Transcribe audio file using Whisper API"""
        logger.info(f"Starting transcription process for: {audio_path}")
        
        logger.info("Calculating audio duration")
        duration = self.get_audio_duration(audio_path)
        
        logger.info("Checking if audio needs to be split")
        chunks = self.split_audio(audio_path)
        
        try:
            logger.info(f"Beginning transcription of {len(chunks)} chunks")
            # Transcribe all chunks
            transcripts = []
            total_chunks = len(chunks)
            
            for i, chunk_path in enumerate(chunks):
                logger.info(f"Transcribing chunk {i+1}/{total_chunks}")
                with open(chunk_path, "rb") as audio_file:
                    result = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=self.language
                    )
                    transcripts.append(result.text)
                
                # Clean up chunk file if it was split
                if len(chunks) > 1:
                    Path(chunk_path).unlink()
                logger.info(f"Successfully transcribed chunk {i+1}/{total_chunks}")
            
            logger.info("All chunks transcribed, combining results")
            raw_transcript = " ".join(transcripts)
            
            logger.info("Saving raw transcript")
            # Save raw transcript
            raw_output_path = Path(audio_path).stem + "_raw_transcript.txt"
            self.save_transcript(raw_transcript, raw_output_path)
            print(f"Raw transcript saved to {raw_output_path}")
            
            logger.info("Starting transcript enhancement")
            enhanced_transcript = self.enhance_transcript(raw_transcript)
            
            # Calculate and display Whisper cost
            whisper_minutes = math.ceil(duration / 60)  # Round up to nearest minute
            whisper_cost = whisper_minutes * 0.006
            print(f"\nWhisper API cost: ${whisper_cost:.4f} ({whisper_minutes} minutes at $0.006/minute)")
            
            if enhanced_transcript != raw_transcript:
                enhanced_output_path = Path(audio_path).stem + "_enhanced_transcript.txt"
                self.save_transcript(enhanced_transcript, enhanced_output_path)
                print(f"Enhanced transcript saved to {enhanced_output_path}")
                return enhanced_transcript
            else:
                print("Warning: Enhancement failed or made no changes, using raw transcript")
                return raw_transcript
            
        except Exception as e:
            logger.error(f"Error during transcription: {str(e)}")
            raise

    def save_transcript(self, transcript, output_path):
        """Save the transcript to a text file in the output directory"""
        # Ensure output directory exists
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        # If output_path is not already in output directory, put it there
        if not str(output_path).startswith(str(output_dir)):
            output_path = output_dir / Path(output_path).name
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(transcript)

if __name__ == "__main__":
    # Load environment variables
    load_dotenv()
    
    # Get API key from environment variables
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    if not OPENAI_API_KEY:
        raise ValueError("Please ensure OPENAI_API_KEY is set in your .env file")
    
    # Check if input is audio or text
    input_path = sys.argv[1] if len(sys.argv) > 1 else "input.txt"
    
    # Create output directory if it doesn't exist
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # Initialize transcriber
    transcriber = AudioTranscriber(OPENAI_API_KEY, language="es")
    
    # Start processing
    start_time = time.time()
    
    if input_path.endswith('.txt'):
        print(f"Processing text file: {input_path}")
        # Read the raw transcript
        with open(input_path, 'r', encoding='utf-8') as f:
            raw_transcript = f.read()
        
        # Enhance the transcript
        enhanced_transcript = transcriber.enhance_transcript(raw_transcript)
        
        # Save enhanced version in output folder
        output_path = output_dir / Path(input_path).name.replace('.txt', '_enhanced.txt')
        transcriber.save_transcript(enhanced_transcript, output_path)
        print(f"Enhanced transcript saved to {output_path}")
    else:
        print(f"Processing audio file: {input_path}")
        if not Path(input_path).exists():
            raise FileNotFoundError(f"File not found: {input_path}")
        transcript = transcriber.transcribe_audio(input_path)
    
    end_time = time.time()
    print(f"Processing completed in {end_time - start_time:.2f} seconds")