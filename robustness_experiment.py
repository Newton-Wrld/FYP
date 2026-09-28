import soundfile as sf
import numpy as np
import librosa
from pydub import AudioSegment
from watermark import embed_watermark, extract_watermark, load_audio_any_format

# ---- Setup ----
SOURCE_FILE = "nokia_test.wav"   # use your known-good test file
WATERMARK = "0123456789abcdef"    # 16-character test watermark
OUTPUT_DIR = "robustness_test_output"

import os
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load and embed once — this is our baseline watermarked file
original_audio, sr = load_audio_any_format(SOURCE_FILE)
watermarked_audio = embed_watermark(original_audio, WATERMARK, strength=0.05)
watermarked_path = os.path.join(OUTPUT_DIR, "watermarked_original.wav")
sf.write(watermarked_path, watermarked_audio, sr)

results = []

def test_extraction(label, audio, sr):
    """Run extraction and record whether it matched."""
    try:
        extracted = extract_watermark(audio, len(WATERMARK))
        matched = (extracted == WATERMARK)
    except Exception as e:
        extracted = f"ERROR: {e}"
        matched = False
    results.append({"test": label, "extracted": extracted, "matched": matched})
    print(f"{label}: {'PASS' if matched else 'FAIL'}  (got: {extracted})")

# ---- Test 1: Original (no transformation) ----
audio, sr2 = sf.read(watermarked_path)
if audio.ndim > 1: audio = audio[:, 0]
test_extraction("Original (baseline)", audio, sr)

# ---- Test 2-4: MP3 compression at various bitrates ----
for bitrate in ["320k", "192k", "128k"]:
    mp3_path = os.path.join(OUTPUT_DIR, f"mp3_{bitrate}.mp3")
    wav_back_path = os.path.join(OUTPUT_DIR, f"mp3_{bitrate}_back.wav")

    sound = AudioSegment.from_wav(watermarked_path)
    sound.export(mp3_path, format="mp3", bitrate=bitrate)

    audio_back, sr_back = librosa.load(mp3_path, sr=sr)
    test_extraction(f"MP3 {bitrate}", audio_back, sr_back)

# ---- Test 5: Added noise ----
noisy_audio = watermarked_audio + np.random.normal(0, 0.005, len(watermarked_audio))
test_extraction("Added noise", noisy_audio, sr)

# ---- Test 6: Volume change ----
quieter_audio = watermarked_audio * 0.5
test_extraction("Volume change (50%)", quieter_audio, sr)

# ---- Test 7: Resampling (down and back up) ----
resampled = librosa.resample(watermarked_audio, orig_sr=sr, target_sr=22050)
resampled_back = librosa.resample(resampled, orig_sr=22050, target_sr=sr)
# Pad/trim to match original length
if len(resampled_back) < len(watermarked_audio):
    resampled_back = np.pad(resampled_back, (0, len(watermarked_audio) - len(resampled_back)))
else:
    resampled_back = resampled_back[:len(watermarked_audio)]
test_extraction("Resampling (22050 and back)", resampled_back, sr)

# ---- Test 8: Cropping (remove first 2 seconds) ----
crop_samples = int(2 * sr)
cropped = watermarked_audio[crop_samples:]
test_extraction("Cropping (first 2s removed)", cropped, sr)

# ---- Test 9: Pitch shift ----
pitch_shifted = librosa.effects.pitch_shift(watermarked_audio, sr=sr, n_steps=2)
test_extraction("Pitch shift (+2 semitones)", pitch_shifted, sr)

# ---- Test 10: Tempo shift ----
tempo_shifted = librosa.effects.time_stretch(watermarked_audio, rate=1.1)
test_extraction("Tempo shift (1.1x speed)", tempo_shifted, sr)

# ---- Summary table ----
print("\n\n=== SUMMARY ===")
print(f"{'Test':<35}{'Result':<10}{'Extracted Value'}")
print("-" * 70)
for r in results:
    status = "PASS" if r["matched"] else "FAIL"
    print(f"{r['test']:<35}{status:<10}{r['extracted']}")