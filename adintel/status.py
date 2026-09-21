"""Summary of what is in the database and how recent runs went."""

from adintel.storage import repository

SUMMARY_SQL = """
SELECT r.slug retailer, c.platform, c.campaign_type, COUNT(*) creatives
FROM creatives c JOIN retailers r ON r.id = c.retailer_id
GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
"""

RUNS_SQL = """
SELECT r.run_uid, rt.slug retailer, r.platform, r.status,
       r.creatives_seen, r.credits_used, r.started_at
FROM runs r JOIN retailers rt ON rt.id = r.retailer_id
ORDER BY r.id DESC LIMIT %s
"""

CREDITS_SQL = "SELECT platform, SUM(credits_used) credits FROM runs GROUP BY 1"

FRESHNESS_SQL = """
SELECT platform, MAX(last_seen_at) last_seen, COUNT(*) total
FROM creatives GROUP BY 1
"""


def report(limit=10):
    connection = repository.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(RUNS_SQL, (limit,))
            runs = cursor.fetchall()
            cursor.execute(SUMMARY_SQL)
            summary = cursor.fetchall()
            cursor.execute(CREDITS_SQL)
            credits = cursor.fetchall()
            cursor.execute(FRESHNESS_SQL)
            freshness = cursor.fetchall()
    finally:
        connection.close()

    lines = [f"recent runs (last {limit})"]
    for row in runs:
        flag = "ok " if row["status"] == "success" else row["status"][:3]
        lines.append(
            f"  {flag} {row['run_uid']}  {row['retailer']:14} {row['platform']:14}"
            f" {row['creatives_seen']:>5} creatives  {row['credits_used']:>3} credits"
        )

    lines.append("\ncreatives by retailer / platform / type")
    for row in summary:
        lines.append(
            f"  {row['retailer']:14} {row['platform']:14} "
            f"{str(row['campaign_type'] or '-'):9} {row['creatives']:>6}"
        )

    lines.append("\ndata freshness")
    for row in freshness:
        lines.append(f"  {row['platform']:14} {row['total']:>6} creatives, "
                     f"last seen {row['last_seen']}")

    lines.append("\ncredits used")
    for row in credits:
        lines.append(f"  {row['platform']:14} {row['credits']}")

    return "\n".join(lines)
