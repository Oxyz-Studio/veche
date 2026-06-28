"""veche CLI.

    python -m veche inspect <map.json>                  # screens + transitions
    python -m veche route   <map.json> --from N --to M  # the action path between two screens

Mapping a new app with the swarm is `scripts/record_swarm.py` + `scripts/build_map.py`
(they emit viz/recording/veche_map.json). Operating an app via a map is `veche.operate`.
"""
from __future__ import annotations

import argparse
import sys

from .portable_map import Map


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="veche")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("inspect", help="list screens and transitions")
    pi.add_argument("map")
    pr = sub.add_parser("route", help="action path between two screens")
    pr.add_argument("map")
    pr.add_argument("--from", dest="frm", required=True)
    pr.add_argument("--to", required=True)
    a = p.parse_args(argv)

    m = Map.load(a.map)
    if a.cmd == "inspect":
        committed = sum(e.committed for e in m.edges)
        app = m.meta.get("app", "?")
        print(f"VECHE map [{app}]: {len(m.nodes)} screens, {len(m.edges)} transitions "
              f"({committed} committed by consensus)")
        for nid in sorted(m.nodes):
            n = m.nodes[nid]
            print(f"  {nid}{('  ' + n.label) if n.label else ''}")
            for e in m.actions(nid, committed_only=False):
                tag = "" if e.committed else "  (uncommitted)"
                args = f" {e.args}" if e.args else ""
                print(f"      --{e.action}{args}--> {e.to_node}  x{e.confirmations}{tag}")
        return 0

    if a.cmd == "route":
        r = m.route(a.frm, a.to)
        note = ""
        if r is None:
            r = m.route(a.frm, a.to, committed_only=False)
            note = "  (includes uncommitted transitions)"
        if r is None:
            print(f"no route from {a.frm} to {a.to}")
            return 1
        print(f"route {a.frm} -> {a.to}  ({len(r)} steps){note}")
        for e in r:
            args = f" {e.args}" if e.args else ""
            tag = "" if e.committed else "  [uncommitted]"
            print(f"  {e.from_node}: {e.action}{args} -> {e.to_node}{tag}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
