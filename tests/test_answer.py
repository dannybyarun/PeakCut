"""A model that is not careful writes a sentence in front of the JSON, a second object after it, or a
code fence around it. The answer is looked for inside the answer rather than demanded of it.

Runs against the code directly, with its own empty data folder."""
import os, sys, tempfile
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-answer-")
sys.path.insert(0, ".")
from studio.ai import _parse
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

check("plain JSON is read", _parse('{"items":[{"hook":"A"}]}'), [{"hook": "A"}])
check("a sentence in front is ignored", _parse('Here you go: {"items":[{"hook":"B"}]}'), [{"hook": "B"}])
check("a sentence after is ignored", _parse('{"items":[{"hook":"C"}]} Hope that helps!'), [{"hook": "C"}])
check("a second object after the first is ignored", _parse('{"items":[{"hook":"D"}]}\n{"items":[{"hook":"E"}]}'), [{"hook": "D"}])
check("a code fence around it is ignored", _parse('```json\n{"items":[{"hook":"F"}]}\n```'), [{"hook": "F"}])
check("two objects in one line: the first is read", _parse('{"items":[{"hook":"H"}]} and {"items":[{"hook":"I"}]}'), [{"hook": "H"}])
try:
    _parse('{"items":[{"hook":"G"}]')
    check("an answer with no closing bracket is refused", False, True)
except Exception:
    check("an answer with no closing bracket is refused", True, True)

print("ALL PASSED" if not fails else f"{len(fails)} FAILED")
sys.exit(1 if fails else 0)
