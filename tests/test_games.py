"""Gaming streams say which game they are. Knowing it changes the rules the AI reads and the tags every
post carries.

Runs against the code directly, with its own empty data folder."""
import os, sys, tempfile
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-games-")
sys.path.insert(0, ".")
from studio import brain, games, live
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)


def _session(title, game=""):
    """A live session that is not recording anything: only the game reading is wanted."""
    d = tempfile.mkdtemp(prefix="pc-games-live-")
    s = live.Session({"title": title, "uploader": "someone", "dir": d, "source": {"url": "", "name": title}},
                     {"game": game})
    return s

# ---- the game is read from the title
check("GTA 6 in a title is GTA VI", games.detect("CLICK THIS STREAM IF YOU WANT GTA 6!")[0], "Grand Theft Auto VI")
check("spelled out is GTA VI", games.detect("grand theft auto vi lets go")[0], "Grand Theft Auto VI")
check("GTA 5 is GTA V", games.detect("GTA V RP tonight")[0], "Grand Theft Auto V")
check("gta5 and gta online are GTA V", games.detect("gta5 gta online")[0], "Grand Theft Auto V")
check("another game is found", games.detect("Fortnite ranked")[0], "Fortnite")
check("a chat stream has no game", games.detect("just chatting with friends")[0], None)
check("GTA 60 seconds is not a game", games.detect("GTA 60 seconds of gameplay")[0], None)

# ---- the tags belong on the post
check("a GTA VI post carries the GTA VI tags", "GTA6" in games.tags_of("gta 6"), True)
check("the tags do not double up", games.tags_of("GTA6Launch") == games.tags_of("gta 6"), True)
check("an unknown game has no tags", games.tags_of("Hades II"), ["HadesII"])

# ---- the tags go on every post, whatever the AI wrote
tidy = brain._tidy({"start": 1, "end": 9, "score": 80, "category": "clutch", "hook": "one vs three",
                     "title": "He got them all", "description": "three of them", "hashtags": ["Gaming", "FPS"],
                     "highlight_words": ["three"]}, 1, 9, game="gta 6")
check("the game's tags are added to the post", "GTA6" in tidy["hashtags"], True)
check("the AI's own tags are kept", "Gaming" in tidy["hashtags"] and "FPS" in tidy["hashtags"], True)
check("the game's tags are not written twice", tidy["hashtags"].count("GTA6"), 1)
plain = brain._tidy({"start": 1, "end": 9, "score": 80, "category": "clutch", "hook": "x", "title": "t",
                     "description": "d", "hashtags": ["Gaming"], "highlight_words": []}, 1, 9)
check("a stream with no game gets no game tags", "GTA6" in plain["hashtags"], False)

# ---- the AI is told which game it is looking at
rules = brain._game_rules("gta 6")
check("the game is named in the extra rules", "Grand Theft Auto VI" in rules, True)
check("the tags are named in the extra rules", "GTA6" in rules, True)
check("a stream with no game gets no extra rules", brain._game_rules(""), "")

# ---- a live session finds its game in the stream's title
check("a live session finds the game in its title", _session("CLICK THIS STREAM IF YOU WANT GTA 6!")._game(),
      "Grand Theft Auto VI")
check("the creator's own setting wins over the title", _session("just chatting", "gta 6")._game(), "Grand Theft Auto VI")
check("a live stream with no game in it says so", _session("morning everyone")._game(), "")

# ---- a short name that means something else is not a game
check("'rust' is not read as the game Rust", games.detect("Rust removal and restoration")[0], None)
check("'the finals' is not read as a game", games.detect("The finals of the world cup")[0], None)

# ---- the people in chat are read under the lock, as a copy
s = _session("morning everyone")
s.chat_users[5] = {"someone"}
people = s.chat_people()
people[5].add("not really there")
check("the people in chat are a copy", s.chat_users[5], {"someone"})

print("ALL PASSED" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
