#!/usr/bin/env python3
"""Transcribe a Russian reel into word-level timings.

GigaAM (CTC) gives the timings, Whisper gives a reference text with proper
spelling of English terms and punctuation. Output: words.json
[{"w": "слово", "s": 1.23, "e": 1.56}, ...] plus whisper.txt for reference.
"""
import json, subprocess, sys, os
import numpy as np, sherpa_onnx

ASR = os.environ.get("ASR_DIR", "/opt/asr")
GIGA = f"{ASR}/sherpa-onnx-nemo-ctc-giga-am-v2-russian-2025-04-19"
WSP = f"{ASR}/sherpa-onnx-whisper-small"
SR = 16000


def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def speech_segments(audio):
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = f"{ASR}/silero_vad.onnx"
    cfg.silero_vad.min_silence_duration = 0.25
    cfg.silero_vad.min_speech_duration = 0.2
    cfg.silero_vad.max_speech_duration = 20
    cfg.sample_rate = SR
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=600)
    win = cfg.silero_vad.window_size
    segs = []
    for i in range(0, len(audio), win):
        vad.accept_waveform(audio[i:i + win])
        while not vad.empty():
            segs.append((vad.front.start, np.array(vad.front.samples)))
            vad.pop()
    vad.flush()
    while not vad.empty():
        segs.append((vad.front.start, np.array(vad.front.samples)))
        vad.pop()
    return segs


def main(src, outdir):
    os.makedirs(outdir, exist_ok=True)
    audio = load_audio(src)
    segs = speech_segments(audio)
    giga = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=f"{GIGA}/model.int8.onnx", tokens=f"{GIGA}/tokens.txt", num_threads=4)
    whisper = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=f"{WSP}/small-encoder.int8.onnx", decoder=f"{WSP}/small-decoder.int8.onnx",
        tokens=f"{WSP}/small-tokens.txt", language="ru", task="transcribe", num_threads=4)
    words, ref = [], []
    for start, samples in segs:
        off = start / SR
        seg_end = off + len(samples) / SR
        s = giga.create_stream(); s.accept_waveform(SR, samples); giga.decode_stream(s)
        r = s.result
        cur = None
        for tok, t in zip(r.tokens, r.timestamps):
            t = off + t
            if tok.startswith("▁") or tok == " " or cur is None:
                if cur and cur["w"]:
                    words.append(cur)
                cur = {"w": tok.lstrip("▁").strip(), "s": round(t, 3), "e": round(t + 0.08, 3)}
            else:
                cur["w"] += tok
                cur["e"] = round(t + 0.08, 3)
        if cur and cur["w"]:
            words.append(cur)
        # words end where the next one starts (within a segment), capped at segment end
        seg_words = [w for w in words if w["s"] >= off - 1e-3]
        for a, b in zip(seg_words, seg_words[1:]):
            a["e"] = round(min(max(a["e"], b["s"] - 0.02), b["s"]), 3)
        if seg_words:
            seg_words[-1]["e"] = round(min(seg_end, seg_words[-1]["s"] + 0.6), 3)
        w = whisper.create_stream(); w.accept_waveform(SR, samples); whisper.decode_stream(w)
        ref.append(f"[{off:6.2f}] {w.result.text.strip()}")
    json.dump(words, open(f"{outdir}/words.json", "w"), ensure_ascii=False, indent=0)
    open(f"{outdir}/whisper.txt", "w").write("\n".join(ref) + "\n")
    print(f"{len(words)} words, {len(segs)} speech segments, audio {len(audio)/SR:.1f}s")
    print("\n".join(ref))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
