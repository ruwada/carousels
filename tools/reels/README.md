# Reel editing

Talking-head video in, polished 1080x1920 reel out: word-by-word subtitles
(active word in lime), hook plate, B-roll motion cards in the channel style,
punch-in zooms, CTA plate, loudness normalised to -14 LUFS.

    ./setup.sh                                  # once per fresh container
    python3 transcribe.py in.mp4 work/          # work/words.json + work/whisper.txt
    # fix spelling in words.json using whisper.txt, write edit.json (see render.py docstring)
    python3 render.py work/edit.json

Card kinds: `stat` (animated number), `text`, `list`, `chat` (messenger mock-up),
`clip` (any video file, e.g. the author's own footage).
