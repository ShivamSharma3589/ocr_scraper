import argparse
import json

from adintel.config.retailers import RETAILERS
from adintel.pipeline import PLATFORMS, run
from adintel.storage import repository


def main(argv=None):
    parser = argparse.ArgumentParser(prog="adintel")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-db", help="create the database and tables")
    init.set_defaults(func=lambda a: repository.apply_schema())

    scrape = sub.add_parser("scrape", help="run one or more platforms for a retailer")
    scrape.add_argument("--retailer", required=True, choices=sorted(RETAILERS))
    scrape.add_argument("--platform", default="all",
                        choices=sorted(PLATFORMS) + ["all"])
    scrape.add_argument("--days", type=int, default=1)
    scrape.add_argument("--limit", type=int, default=None)
    scrape.add_argument("--no-db", action="store_true")

    st = sub.add_parser("status", help="show recent runs and what is stored")
    st.add_argument("--limit", type=int, default=10)

    ask = sub.add_parser("ask", help="ask a question of the database in English")
    ask.add_argument("question")
    ask.add_argument("--model", default=None)
    ask.add_argument("--sql-only", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "init-db":
        repository.apply_schema()
        print("schema applied")
        return 0

    if args.command == "status":
        from adintel import status
        print(status.report(args.limit))
        return 0

    if args.command == "ask":
        from adintel import insights
        if args.sql_only:
            problem = insights.check_ollama(model=args.model)
            if problem:
                print(f"error: {problem}")
                return 1
            print(insights.generate_sql(args.question, model=args.model))
            return 0
        print(json.dumps(insights.ask(args.question, model=args.model), indent=2))
        return 0

    platforms = PLATFORMS if args.platform == "all" else (args.platform,)
    for platform in platforms:
        try:
            summary = run(platform, args.retailer, days=args.days,
                          limit=args.limit, persist=not args.no_db)
            print(json.dumps(summary, indent=2))
        except Exception as exc:
            print(f"{platform}: FAILED - {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
