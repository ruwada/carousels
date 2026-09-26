#!/usr/bin/env python3
"""Find and fetch vertical B-roll from Pexels.

    python3 pexels.py search "man typing laptop" [more queries...]
    python3 pexels.py get 12893567 broll/        # saves broll/12893567.mp4

The key comes from the environment's API credential for api.pexels.com, or from PEXELS_API_KEY.

Search skips clips whose title mentions women, couples or children (the channel's B-roll rule),
but titles are not enough: always look at several frames of every clip before using it.
"""
import json, os, re, sys, urllib.parse, urllib.request

API = "https://api.pexels.com/videos"
SKIP = re.compile(r"wom[ae]n|girl|lady|female|her-|mother|bride|couple|family|kid|child|wine|beer|bar-|party|dance", re.I)


def call(url):
    headers = {"User-Agent": "reels"}
    if os.environ.get("PEXELS_API_KEY"):  # otherwise the environment's API credential for api.pexels.com is used
        headers["Authorization"] = os.environ["PEXELS_API_KEY"]
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=headers)))


def best_file(video):
    """Smallest portrait file that is at least 1920 px tall."""
    files = [f for f in video["video_files"] if f["height"] and f["height"] >= 1920 and f["width"] < f["height"]]
    return min(files, key=lambda f: f["height"]) if files else None


def search(query, n=12):
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "size": "large", "per_page": n})
    for v in call(f"{API}/search?{q}")["videos"]:
        slug = v["url"].rstrip("/").split("/")[-1]
        f = best_file(v)
        if f and not SKIP.search(slug):
            print(f"{v['id']:>10} {v['duration']:>3}s  {slug[:70]}")


def get(vid, outdir):
    f = best_file(call(f"{API}/videos/{vid}"))
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{vid}.mp4")
    req = urllib.request.Request(f["link"], headers={"User-Agent": "reels"})
    with urllib.request.urlopen(req) as r, open(path, "wb") as out:
        out.write(r.read())
    print(path)


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    if cmd == "search":
        for query in rest:
            print(f"== {query}")
            search(query)
    elif cmd == "get":
        get(rest[0], rest[1] if len(rest) > 1 else ".")
