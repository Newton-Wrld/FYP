import soundfile as sf
import numpy as np
from watermark import extract_watermark

# Step 1: Load the watermarked WAV
audio, sr = sf.read("nokia_watermarked.wav")
if audio.ndim > 1:
    audio = audio[:, 0]

# Step 2: Save it as MP3 (this compresses it, simulating real-world sharing)
try:
    sf.write("nokia_watermarked_compressed.mp3", audio, sr)
    print("Saved as MP3 successfully")
except Exception as e:
    print(f"Could not write MP3 directly: {e}")
    print("We'll need a different method — see note below.")
    exit()

# Step 3: Reload the MP3 back into a WAV-like array
import librosa
reloaded_audio, sr2 = librosa.load("nokia_watermarked_compressed.mp3", sr=sr)

# Step 4: Try to extract the watermark from the compressed-then-reloaded audio
watermark_id = "TRK001"
extracted = extract_watermark(reloaded_audio, len(watermark_id))

print(f"Original watermark:  {watermark_id}")
print(f"Extracted watermark: {extracted}")

if extracted == watermark_id:
    print("SURVIVED MP3 compression!")
else:
    print("DID NOT SURVIVE MP3 compression — watermark was damaged.")