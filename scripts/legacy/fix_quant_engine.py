import pathlib

f = pathlib.Path(".github/workflows/quant_engine.yml")
lines = f.read_text(encoding="utf-8").splitlines()

# Keep the real "name:" line, then skip the duplicate stub (lines 2-6),
# and resume from the real "on:" line (line 7 onward = index 6).
fixed_lines = [lines[0]] + lines[6:]

f.write_text("\n".join(fixed_lines) + "\n", encoding="utf-8", newline="\n")
print("done")
