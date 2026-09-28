import numpy as np
import pywt
import soundfile as sf

def text_to_bits(text):
    """Convert a text string into a list of 0s and 1s"""
    bits = []
    for char in text:
        byte = format(ord(char), '08b')
        bits.extend([int(b) for b in byte])
    return bits

def bits_to_text(bits):
    """Convert a list of 0s and 1s back into text"""
    chars = []
    for i in range(0, len(bits), 8):
        byte = bits[i:i+8]
        if len(byte) < 8:
            break
        char_code = int(''.join(str(b) for b in byte), 2)
        chars.append(chr(char_code))
    return ''.join(chars)

def embed_watermark(audio, watermark_text, strength=0.01):
    bits = text_to_bits(watermark_text)

    coeffs = pywt.wavedec(audio, 'db4', level=3, mode='periodization')
    detail_coeffs = coeffs[1].copy()

    if len(bits) > len(detail_coeffs):
        raise ValueError("Watermark too long for this audio length")

    for i, bit in enumerate(bits):
        if bit == 1:
            detail_coeffs[i] = abs(detail_coeffs[i]) + strength
        else:
            detail_coeffs[i] = -abs(detail_coeffs[i]) - strength

    coeffs[1] = detail_coeffs
    watermarked_audio = pywt.waverec(coeffs, 'db4', mode='periodization')
    return watermarked_audio

def extract_watermark(audio, watermark_length_chars):
    num_bits = watermark_length_chars * 8

    coeffs = pywt.wavedec(audio, 'db4', level=3, mode='periodization')
    detail_coeffs = coeffs[1]

    bits = []
    for i in range(num_bits):
        bits.append(1 if detail_coeffs[i] > 0 else 0)

    return bits_to_text(bits)


if __name__ == "__main__":
    original_audio, sr = sf.read("nokia_test.wav")

    if original_audio.ndim > 1:
        original_audio = original_audio[:, 0]

    watermark_id = "TRK001"
    print(f"Embedding watermark: {watermark_id}")

    watermarked_audio = embed_watermark(original_audio, watermark_id)
    sf.write("nokia_watermarked.wav", watermarked_audio, sr)
    print("Saved watermarked file as nokia_watermarked.wav")

    reloaded_audio, sr2 = sf.read("nokia_watermarked.wav")
    if reloaded_audio.ndim > 1:
        reloaded_audio = reloaded_audio[:, 0]

    extracted = extract_watermark(reloaded_audio, len(watermark_id))
    print(f"Extracted watermark: {extracted}")

    if extracted == watermark_id:
        print("SUCCESS: Watermark matches!")
    else:
        print("MISMATCH: Something went wrong.")

        import librosa

def load_audio_any_format(path):
    """Load WAV or MP3, return (audio, sample_rate) as mono."""
    try:
        audio, sr = sf.read(path)
    except Exception:
        audio, sr = librosa.load(path, sr=None)
    if hasattr(audio, "ndim") and audio.ndim > 1:
        audio = audio[:, 0]
    return audio, sr

def generate_watermarked_copy(source_path, watermark_text, output_path):
    """Load a track, embed a watermark, save the result. Returns the watermark text used."""
    audio, sr = load_audio_any_format(source_path)
    watermarked = embed_watermark(audio, watermark_text)
    sf.write(output_path, watermarked, sr)
    return watermark_text