"""Print CLI.md option tables for every scraper, generated from the argparse definitions."""
import argparse, sys
sys.path.insert(0, ".")
from higgsfield_scraper.cli import build_parser
from higgsfield_scraper.core.registry import available
ap = build_parser()
scr = next(a for a in ap._subparsers._group_actions[0].choices["scrape"]._actions if isinstance(a, argparse._SubParsersAction))
COMMON = None
def rows(p):
    out = []
    for a in p._actions:
        if not a.option_strings or a.dest == "help": continue
        out.append(a)
    return out
def fmt(a):
    opt = " / ".join(f"`{o}`" for o in a.option_strings)
    if isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._CountAction)): acc = "flag"
    elif a.choices: acc = " ".join(f"`{c}`" for c in a.choices)
    else: acc = a.metavar or a.dest.upper()
    d = a.default
    flag = isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._CountAction))
    d = "off" if flag else ("—" if d is None else f"`{d}`")
    h = (a.help or "").replace("%(default)s", str(a.default)).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    return f"| {opt} | {d} | {acc} | {h} |"
pars = {n: scr.choices[n] for n in scr.choices}
common = set.intersection(*[{a.dest for a in rows(p)} for p in pars.values()])
REG = available(); order = list(REG)
limits = set.intersection(*[{a.dest for a in rows(pars[n])} for n in order if n != "pricing"]) - common
out = ["<!-- generated from the argparse definitions; regenerate with scripts/gen_cli_tables.py -->", ""]
out += ["### Shared options (every scraper)", "", "| Option | Default | Accepts | Meaning |", "|---|---|---|---|"]
seen=set()
for a in rows(pars["community"]):
    if a.dest in common and a.dest not in seen: seen.add(a.dest); out.append(fmt(a))
out += ["", "### Limits and media (" + ", ".join(n for n in order if n != "pricing") + ")", "", "| Option | Default | Accepts | Meaning |", "|---|---|---|---|"]
for a in rows(pars["community"]):
    if a.dest in limits and a.dest not in seen: seen.add(a.dest); out.append(fmt(a))
for n in order:
    sdef = REG[n]
    out += ["", f"### `scrape {n}`", "", sdef.description, ""]
    own = [a for a in rows(pars[n]) if a.dest not in common and a.dest not in limits]
    if own:
        out += ["| Option | Default | Accepts | Meaning |", "|---|---|---|---|"] + [fmt(a) for a in own]
    if sdef.examples:
        out += ["", "```bash"] + [("python -m higgsfield_scraper " + e if not e.startswith("python") else e).replace("python -m higgsfield_scraper python -m higgsfield_scraper","python -m higgsfield_scraper") for e in sdef.examples] + ["```"]
print("\n".join(out))
