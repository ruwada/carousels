#!/usr/bin/env bash
# Prepares a fresh container for reel editing: ffmpeg, speech models, brand fonts.
set -euo pipefail
command -v ffmpeg >/dev/null || { apt-get update -q && apt-get install -y -q ffmpeg; }
python3 -m pip install -q sherpa-onnx numpy playwright
ASR=/opt/asr; mkdir -p $ASR; cd $ASR
REL=https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models
[ -f silero_vad.onnx ] || curl -sSL -o silero_vad.onnx $REL/silero_vad.onnx
for m in sherpa-onnx-nemo-ctc-giga-am-v2-russian-2025-04-19 sherpa-onnx-whisper-small; do
  [ -d $m ] || { curl -sSL $REL/$m.tar.bz2 | tar xj; }
done
rm -f sherpa-onnx-whisper-small/small-{encoder,decoder}.onnx  # keep int8 only
F=/usr/local/share/fonts/brand; mkdir -p $F
for spec in Unbounded:800 Unbounded:900 Manrope:700 Manrope:800; do
  fam=${spec%%:*}; w=${spec##*:}
  [ -f $F/$fam-$w.ttf ] || curl -sS -o $F/$fam-$w.ttf \
    "$(curl -sS "https://fonts.googleapis.com/css2?family=$fam:wght@$w" | grep -oE 'https://[^)]+\.ttf' | head -1)"
done
# monospace for the "terminal" card theme
[ -f $F/JetBrainsMono-800.ttf ] || curl -sS -o $F/JetBrainsMono-800.ttf \
  "$(curl -sS "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@800" | grep -oE 'https://[^)]+\.ttf' | head -1)"
fc-cache -f >/dev/null
echo "reel tools ready"
