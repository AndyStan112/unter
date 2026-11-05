"""Renders a report.ready event as an email: plain text plus HTML, every value escaped.

Standard library only. The content comes from the report: summary, a per-zone metrics table,
proposals grouped by zone, and the zones that were skipped. Times are shown in UTC.
"""
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape

APPROVAL = 'Nothing has been applied. A person approves proposals in the Unter dashboard.'
METRICS = [  # (heading, how to show it from a zone summary)
    ('Zone', lambda z: z['zone']),
    ('Requests', lambda z: z['requests']),
    ('Per hour', lambda z: z.get('requests_per_hour')),
    ('Unmatched', lambda z: percent(z.get('unmatched_rate'))),
    ('Cancelled', lambda z: percent(z.get('cancel_rate'))),
    ('Worst p90 wait', lambda z: seconds(z.get('worst_p90_wait_s'))),
    ('Net flow', lambda z: z.get('net_flow')),
    ('Drivers now', lambda z: (z.get('supply_now') or {}).get('available')),
    ('Demand/supply', lambda z: z.get('demand_supply_ratio')),
    ('Active rules', lambda z: active(z)),
]


def percent(value) -> str:
    return '—' if value is None else f'{value:.0%}'


def seconds(value) -> str:
    return '—' if value is None else f'{value:.0f} s'


def when(value: str) -> str:
    return datetime.fromisoformat(value).strftime('%d %b %Y %H:%M UTC')


def span(params: dict) -> str:
    starts, ends = datetime.fromisoformat(params['starts_at']), datetime.fromisoformat(params['ends_at'])
    end = ends.strftime('%H:%M') if starts.date() == ends.date() else ends.strftime('%d %b %H:%M')
    return f"{starts.strftime('%d %b %Y %H:%M')}–{end} UTC"


def active(zone: dict) -> str:
    parts = []
    if zone.get('active_surge'):
        parts.append(f"surge x{zone['active_surge']['multiplier']}")
    if zone.get('active_incentive'):
        parts.append(f"bonus {zone['active_incentive']['bonus_per_trip']} RON")
    return ', '.join(parts) or '—'


def value(proposal: dict) -> str:
    params = proposal['params']
    if proposal['type'] == 'surge':
        return f"Surge x{params['multiplier']}"
    return f"Driver bonus {params['bonus_per_trip']} RON per trip"


def by_zone(proposals: list[dict]) -> dict[str, list[dict]]:
    grouped = {}
    for proposal in proposals:
        grouped.setdefault(proposal['zone'], []).append(proposal)
    return grouped


def subject(data: dict) -> str:
    count = len(data['proposals'])
    text = f"Unter surge & incentive report, {when(data['window']['to'])}: "
    text += f'{count} proposal(s)' if count else 'no proposals'
    return text + (' [manual run]' if data.get('source') == 'manual' else '')


def cell(item) -> str:
    return '—' if item is None else str(item)


def text_body(data: dict) -> str:
    window = data['window']
    lines = [f"Window: {when(window['from'])} to {when(window['to'])} ({window['hours']} h)", '', data['summary'], '']
    lines.append('PROPOSALS' if data['proposals'] else 'No proposals for this window.')
    for zone, proposals in by_zone(data['proposals']).items():
        lines.append(f'\n{zone}')
        for p in proposals:
            lines += [f'  - {value(p)}, {span(p["params"])}', f'    {p["reason"]}']
    if data.get('skipped'):
        lines += ['', 'SKIPPED'] + [f"  - {s['zone']}: {s['reason']}" for s in data['skipped']]
    lines += ['', 'ZONES']
    rows = [[heading for heading, _ in METRICS]] + [[cell(show(z)) for _, show in METRICS] for z in data['zones']]
    widths = [max(len(row[i]) for row in rows) for i in range(len(METRICS))]
    lines += ['  ' + '  '.join(c.ljust(w) for c, w in zip(row, widths)).rstrip() for row in rows]
    lines += ['', APPROVAL, f"Report {data['report_id']}"
              + (f", text by {data['model']}" if data.get('explained_by') == 'model' else ', template text')]
    return '\n'.join(lines) + '\n'


def html_body(data: dict) -> str:
    e = lambda item: escape(cell(item))
    window = data['window']
    th = 'style="text-align:left;padding:4px 8px;border-bottom:1px solid #ccc"'
    td = 'style="padding:4px 8px;border-bottom:1px solid #eee"'
    parts = ['<div style="font-family:system-ui,sans-serif;font-size:14px;color:#222;max-width:900px">',
             f'<h2 style="margin:0 0 4px">Surge &amp; incentive report</h2>',
             f'<p style="color:#666;margin:0 0 16px">{e(when(window["from"]))} to {e(when(window["to"]))} '
             f'({e(window["hours"])} h)</p>',
             f'<p>{e(data["summary"])}</p>', '<h3>Proposals</h3>']
    if not data['proposals']:
        parts.append('<p>No proposals for this window.</p>')
    for zone, proposals in by_zone(data['proposals']).items():
        parts.append(f'<h4 style="margin:12px 0 4px">{e(zone)}</h4><ul style="margin:0;padding-left:20px">')
        for p in proposals:
            parts.append(f'<li><strong>{e(value(p))}</strong>, {e(span(p["params"]))}<br>{e(p["reason"])}</li>')
        parts.append('</ul>')
    if data.get('skipped'):
        parts.append('<h3>Skipped</h3><ul>' + ''.join(f'<li>{e(s["zone"])}: {e(s["reason"])}</li>'
                                                      for s in data['skipped']) + '</ul>')
    parts.append('<h3>Zones</h3><table style="border-collapse:collapse"><tr>'
                 + ''.join(f'<th {th}>{e(h)}</th>' for h, _ in METRICS) + '</tr>')
    for z in data['zones']:
        parts.append('<tr>' + ''.join(f'<td {td}>{e(show(z))}</td>' for _, show in METRICS) + '</tr>')
    parts += ['</table>', f'<p style="margin-top:16px"><strong>{e(APPROVAL)}</strong></p>',
              f'<p style="color:#888;font-size:12px">Report {e(data["report_id"])}</p></div>']
    return '\n'.join(parts)


def build_message(data: dict, sender: str) -> EmailMessage:
    message = EmailMessage()
    message['Subject'] = subject(data)
    message['From'] = sender
    message['To'] = ', '.join(data['recipients'])
    message['Message-ID'] = make_msgid(idstring=f"report-{data['report_id']}")
    message.set_content(text_body(data))
    message.add_alternative(html_body(data), subtype='html')
    return message
