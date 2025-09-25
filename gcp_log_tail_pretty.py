#!/usr/bin/env python3
# gcp_log_tail_pretty.py  (high-level client version)
import os, re, time, signal, argparse, json
from collections import Counter, deque
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# High-level client works on all recent versions
from google.cloud import logging as gcl

load_dotenv()

SEV_COLOR = {
    "DEBUG":"cyan","INFO":"white","NOTICE":"white",
    "WARNING":"yellow","ERROR":"red",
    "CRITICAL":"bright_red","ALERT":"bright_red","EMERGENCY":"bright_red"
}

def human_ts(ts):
    if not ts: return "n/a"
    if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone().strftime("%Y-%m-%d %H:%M:%S")

def pick_payload(entry):
    p = entry.payload
    if p is None: return ""
    if isinstance(p, dict):
        for k in ("message","msg","error","err","Exception","stack","textPayload"):
            if k in p and p[k]:
                return str(p[k])
        return json.dumps(p, ensure_ascii=False)
    return str(p)

ID_PAT = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
DIGITS_PAT = re.compile(r"\d{3,}")
WS_PAT = re.compile(r"\s+")
def signature_of(message: str) -> str:
    s = (message or "").strip()
    s = s.splitlines()[0] if s else s
    s = ID_PAT.sub("<id>", s)
    s = DIGITS_PAT.sub("<num>", s)
    s = WS_PAT.sub(" ", s)
    return s[:160] if s else "<empty>"

def build_filter(args):
    parts = []
    if args.filter:
        parts.append(f"({args.filter})")
    if args.severity:
        parts.append(f"severity>={args.severity}")
    if args.service == "cloud_run":
        parts.append('resource.type="cloud_run_revision"')
    elif args.service == "cloud_functions":
        parts.append('resource.type="cloud_function"')
    elif args.service == "gce":
        parts.append('resource.type="gce_instance"')

    # Map --exclude "foo" to NOT (…) across likely fields
    if args.exclude:
        for ex in args.exclude:
            exq = ex.replace('"', r'\"')
            parts.append(
                'NOT ('
                f'textPayload:"{exq}" OR '
                f'jsonPayload.message:"{exq}" OR '
                f'jsonPayload.error:"{exq}" OR '
                f'jsonPayload.err:"{exq}" OR '
                f'jsonPayload.stack:"{exq}"'
                ')'
            )
    return " AND ".join(parts) if parts else None


def main():
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.text import Text

    console = Console()

    parser = argparse.ArgumentParser(description="Pretty tail for Google Cloud logs")
    parser.add_argument("--project", default=os.getenv("CLOUDSDK_CORE_PROJECT"),
                        help="Project ID (or set CLOUDSDK_CORE_PROJECT in .env)")
    parser.add_argument("--severity", choices=["DEBUG","INFO","NOTICE","WARNING","ERROR","CRITICAL","ALERT","EMERGENCY"],
                        default="ERROR")
    parser.add_argument("--service", choices=["cloud_run","cloud_functions","gce"])
    parser.add_argument("--filter", help="Additional Logging filter expression")
    parser.add_argument("--exclude", action="append", help='Exclude text (repeatable). Example: --exclude "webpack"')
    parser.add_argument("--interval", type=int, default=5, help="Polling seconds")
    parser.add_argument("--late-slack", type=int, default=2, help="Seconds to keep cursor behind newest")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--keep", type=int, default=50, help="Show last N entries in the table")
    parser.add_argument("--top", type=int, default=10, help="Show top N signatures")
    parser.add_argument("--width-msg", type=int, default=100, help="Max message width in table")
    args = parser.parse_args()

    if not args.project:
        console.print("[red]Missing project id.[/red] Set --project or CLOUDSDK_CORE_PROJECT in .env")
        raise SystemExit(1)

    client = gcl.Client(project=args.project)

    def make_tables(rows, top_counts):
        t = Table(show_header=True, header_style="bold", expand=True)
        t.add_column("Time", width=19)
        t.add_column("Sev", width=8)
        t.add_column("Service", width=18, overflow="fold")
        t.add_column("Message", overflow="fold", max_width=args.width_msg)
        for r in rows:
            sev_text = Text(r["sev"], style=SEV_COLOR.get(r["sev"], "white"))
            t.add_row(r["time"], sev_text, r["svc"], r["msg"])
        lines = [f"[{cnt:>4}] {sig}" for sig, cnt in top_counts]
        summary = Panel("\n".join(lines) or "No errors yet.", title="Top errors (by signature)", border_style="cyan")
        return t, summary

    filt_base = build_filter(args)
    tail_rows = deque(maxlen=args.keep)
    sig_counter = Counter()
    seen = set()
    cursor = datetime.now(timezone.utc) - timedelta(seconds=args.interval * 2)

    stop = False
    def _stop(*_): 
        nonlocal stop
        stop = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    with Live(console=console, refresh_per_second=8, screen=True) as live:
        while not stop:
            time_filter = f'timestamp>="{cursor.isoformat()}"'
            filt = " AND ".join(x for x in [time_filter, filt_base] if x)

            newest = cursor
            try:
                entries = client.list_entries(
                    filter_=filt,
                    order_by=gcl.DESCENDING,
                    page_size=args.page_size,
                )
                for e in entries:
                    insert_id = getattr(e, "insert_id", None) or f"{e.timestamp}-{e.log_name}"
                    if insert_id in seen:
                        continue
                    seen.add(insert_id)

                    ts = human_ts(e.timestamp)
                    sev = str(getattr(e, "severity", "UNKNOWN"))
                    rtype = e.resource.type if e.resource else "unknown"
                    svc = rtype
                    if e.resource and getattr(e.resource, "labels", None):
                        svc = e.resource.labels.get("service_name", svc)
                    msg = pick_payload(e)
                    first_line = msg.splitlines()[0] if msg else ""
                    preview = (first_line[:args.width_msg] +
                               ("…" if len(first_line) > args.width_msg else ""))

                    tail_rows.appendleft({"time": ts, "sev": sev, "svc": svc, "msg": preview})
                    sig_counter[signature_of(msg or "")] += 1

                    if e.timestamp and e.timestamp > newest:
                        newest = e.timestamp

            except Exception as err:
                console.log(f"[red]Logging API error:[/red] {err}")

            cursor = (newest or cursor) - timedelta(seconds=args.late_slack)

            # rebuild the two panels
            top_counts = sig_counter.most_common(args.top)
            table, summary = make_tables(list(tail_rows), top_counts)

            # Use live.update, not console.update
            live.update(Panel.fit(table,
                                  title=f"Project: {args.project} | severity>={args.severity}",
                                  border_style="magenta"))
            console.print(summary)

            time.sleep(args.interval)

if __name__ == "__main__":
    main()
