"""
How fast, and how much memory: Piper and Vosk inside the Dot's Debian (or the Pi's copy).

Piper says a typical question into a file, then Vosk listens to that file twice: once with
Harald's word list (how he listens to questions) and once freely. Nothing is played aloud
and nothing leaves the machine.
"""
import glob
import json
import os
import resource
import subprocess
import sys
import time
import wave

QUESTION = "What time is it in Texas?"
ANSWER = "In Texas it's eleven forty seven in the morning. That's six hours behind you."
WAV = "/tmp/bench-question.wav"


def mem_mb(field):
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith(field + ":"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


def available_mb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


def piper(text, out):
    voice = sorted(glob.glob("/opt/voices/*.onnx"))[0]
    t = time.time()
    p = subprocess.run(["/opt/piper/piper", "--model", voice, "--output_file", out],
                       input=text.encode(), capture_output=True)
    took = time.time() - t
    if p.returncode != 0:
        print("  Piper failed:", p.stderr.decode(errors="replace")[-300:])
        return None
    with wave.open(out) as w:
        secs = w.getnframes() / w.getframerate()
    return took, secs


def listen(model, vocab):
    import vosk
    with wave.open(WAV) as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    t = time.time()
    rec = vosk.KaldiRecognizer(model, rate, json.dumps(vocab + ["[unk]"])) if vocab \
        else vosk.KaldiRecognizer(model, rate)
    for i in range(0, len(frames), 8000):
        rec.AcceptWaveform(frames[i:i + 8000])
    text = json.loads(rec.FinalResult()).get("text", "")
    return time.time() - t, text


def main():
    print(f"  processors: {os.cpu_count()}, memory free for programs: {available_mb()} MB, "
          f"Python {sys.version.split()[0]}")

    r = piper(QUESTION, WAV)
    if not r:
        return 1
    r2 = piper(ANSWER, "/tmp/bench-answer.wav")
    piper_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024
    print(f"  Piper: a {r2[1]:.1f} s sentence took {r2[0]:.1f} s to make "
          f"(peak memory {piper_peak} MB)")

    import vosk
    vosk.SetLogLevel(-1)
    t = time.time()
    model = vosk.Model("/opt/vosk-model")
    print(f"  Vosk: loading the model took {time.time() - t:.1f} s, "
          f"memory now {mem_mb('VmRSS')} MB")
    with open("/opt/harald/vocab.json") as f:
        grammar = json.load(f)
    words = [w for w in grammar if " " not in w]
    took, text = listen(model, words)
    print(f"  Vosk with Harald's words:   {took:.1f} s for {r[1]:.1f} s of speech -> \"{text}\"")
    if len(grammar) > len(words):
        took, text = listen(model, grammar)
        print(f"  Vosk with words + phrases:  {took:.1f} s for {r[1]:.1f} s of speech -> \"{text}\"")
    took, text = listen(model, None)
    print(f"  Vosk listening freely:      {took:.1f} s for {r[1]:.1f} s of speech -> \"{text}\"")
    print(f"  peak memory while listening: {mem_mb('VmHWM')} MB; "
          f"free for programs now: {available_mb()} MB")
    for f in (WAV, "/tmp/bench-answer.wav"):
        try:
            os.remove(f)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
