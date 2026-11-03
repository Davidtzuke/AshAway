"""AshAway on the command line. No account, and nothing about the traveller is stored (NFR7).

    ashaway places
    ashaway assess rhodes 2023-07-18 2023-07-24
    ashaway compare rhodes volos 2023-07-18 2023-07-24
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .assess import Assessment, Assessor, load_destinations
from .model.bundle import DEFAULT_BUNDLE_DIR, load_bundle
from .request import RequestRejected

EXIT_OK, EXIT_REJECTED = 0, 2
UPDATE_LOG = "logs/feed_updates.jsonl"


def format_assessment(a: Assessment) -> str:
    lines = [
        f"{a.destination}, {a.start} to {a.end}",
        f"Assessed as of {a.as_of}. Generated {a.generated_at}. Model {a.model_version}.",
        "",
        a.level_text,
    ]
    if a.level is None and a.forecast_level:
        lines.append(f"The weather model alone says {a.forecast_level}, but that is not enough on its own.")
    if a.days:
        lines += ["", "Risk per day"]
        lines += [f"  {d.date}  {d.level:<7} score {d.probability:.2f}" for d in a.days]
    if a.reasons:
        lines += ["", "Main reasons"] + [f"  - {r}" for r in a.reasons]
    if a.evidence:
        lines += ["", "Evidence"]
        lines += [f"  [{e.kind.value.upper()}] {e.observed_on}, {e.source}: {e.summary}" for e in a.evidence]
    if a.warnings:
        lines += ["", "Warnings"] + [f"  ! {w}" for w in a.warnings]
    if a.alternatives:
        lines += ["", "Lower estimated risk on the same dates"]
        lines += [f"  - {alt['name']}: {alt['level']} (peak score {alt['peak_probability']:.2f})" for alt in a.alternatives]
        lines.append("  A lower estimate is not proof of safety.")
    lines += ["", a.disclaimer]
    return "\n".join(lines)


def format_comparison(rows: list[dict]) -> str:
    out = [f"{'Destination':<18}{'Risk':<24}{'Peak score':>11}{'Evidence age':>14}{'Sources':>10}"]
    for r in rows:
        peak = f"{r['peak_probability']:.2f}" if r["peak_probability"] is not None else "-"
        age = f"{r['evidence_age_days']} days" if r["evidence_age_days"] is not None else "-"
        out.append(f"{r['destination']:<18}{r['level']:<24}{peak:>11}{age:>14}{r['sources_available']:>10}")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ashaway", description="Wildfire-risk advice for holiday destinations in Greece.")
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE_DIR), help="model version directory")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("places", help="list supported destinations")
    assess = sub.add_parser("assess", help="assess one destination")
    assess.add_argument("place")
    assess.add_argument("start")
    assess.add_argument("end")
    assess.add_argument("--json", action="store_true")
    compare = sub.add_parser("compare", help="compare destinations on the same dates")
    compare.add_argument("places", nargs="+", metavar="place")
    compare.add_argument("start")
    compare.add_argument("end")
    return ap


def main(argv: list[str] | None = None, assessor: Assessor | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "places":
        print("\n".join(sorted(load_destinations()["name"])))
        return EXIT_OK
    assessor = assessor or Assessor(load_bundle(args.bundle), log_path=UPDATE_LOG)
    try:
        if args.command == "assess":
            result = assessor.assess(args.place, args.start, args.end)
            print(json.dumps(result.to_dict(), indent=2, default=_json_value) if args.json else format_assessment(result))
        else:
            if len(args.places) < 2:
                print("A comparison needs at least two destinations.", file=sys.stderr)
                return EXIT_REJECTED
            print(format_comparison(assessor.compare(args.places, args.start, args.end)))
    except RequestRejected as rejected:
        print(rejected.message, file=sys.stderr)
        return EXIT_REJECTED
    return EXIT_OK


def _json_value(value):
    if isinstance(value, date):
        return value.isoformat()
    return str(getattr(value, "value", value))


if __name__ == "__main__":
    sys.exit(main())
