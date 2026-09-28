import librosa
import soundfile as sf

# Load the MP3 (librosa reads it and converts to a numerical array)
audio, sample_rate = librosa.load("NOKIA.mp3", sr=None)

# Save it as a WAV file
sf.write("nokia_test.wav", audio, sample_rate)

print("Done! Saved as nokia_test.wav")
print(f"Sample rate: {sample_rate}")
print(f"Duration: {len(audio) / sample_rate:.2f} seconds")