"""Password-protected human review: list results, confirm or change AI levels."""

import os
from db import get_connection
from app.rubric import get_level_display, get_level_keys

LEVELS = [get_level_display(level) for level in get_level_keys()]


def _row(tag, *cells):
    """Render an HTML table row."""
    return f"<tr>{''.join(f'<{tag}>{c}</{tag}>' for c in cells)}</tr>"


def render_review_html(password_ok: bool, rows: list, pw: str = "", msg: str = "") -> str:
    """Return the full review page HTML; pw is echoed into hidden fields (never shown)."""
    login = "" if password_ok else """
<form method="post" action="/review/login" style="margin:1em">
  <input name="password" type="password" placeholder="Reviewer password" style="padding:6px">
  <button type="submit">Login</button>
</form>"""

    table = ""
    if password_ok and rows:
        opts = "".join(f'<option value="{l}">{l}</option>' for l in LEVELS)
        table_rows = ""
        for r in rows:
            sid = r["session_id"][:8]
            table_rows += f"""<tr>
  <td>{sid}</td><td>{r['dimension']}</td><td>{r['criterion']}</td>
  <td><em>{r['level']}</em></td>
  <td style="max-width:200px;font-size:.85em">{r['evidence'] or '—'}</td>
  <td>
    <form method="post" action="/review/confirm" style="display:flex;gap:4px;flex-wrap:wrap">
      <input type="hidden" name="pw" value="{pw}">
      <input type="hidden" name="score_id" value="{r['id']}">
      <input type="hidden" name="session_id" value="{r['session_id']}">
      <select name="level">{opts}</select>
      <button name="action" value="confirm">✓ Confirm</button>
      <button name="action" value="change">✎ Change</button>
    </form>
  </td>
</tr>"""
        table = f"""<table border="1" cellpadding="4" style="border-collapse:collapse;font-size:.9em">
<thead>{_row('th','Session','Dimension','Criterion','AI level','Quote','Action')}</thead>
<tbody>{table_rows}</tbody></table>"""
    elif password_ok:
        table = "<p>No results to review.</p>"

    notice = f'<p style="color:green">{msg}</p>' if msg else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>SabiLab Review</title></head><body>
<h2>SabiLab Reviewer</h2>{notice}{login}{table}
</body></html>"""


def list_review_rows() -> list:
    """Fetch all score rows joined with routing from results."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT s.id, s.session_id, s.dimension, s.criterion, s.level, s.evidence,
                   r.routing
            FROM scores s LEFT JOIN results r ON s.session_id = r.session_id
            ORDER BY r.routing DESC, s.session_id, s.id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def apply_review(score_id: int, session_id: str, new_level: str, action: str):
    """Update score level and upgrade badge/result tier to Human-verified."""
    import json
    from datetime import datetime, timezone
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        if action == "change":
            conn.execute("UPDATE scores SET level = ? WHERE id = ?", (new_level, score_id))
        conn.execute(
            "UPDATE results SET routing = 'Human-verified' WHERE session_id = ?", (session_id,)
        )
        conn.execute(
            "UPDATE badges SET tier = 'Human-verified' WHERE session_id = ?", (session_id,)
        )
        conn.execute(
            "INSERT INTO events (session_id, type, time, details) VALUES (?, 'human_review', ?, ?)",
            (session_id, now, json.dumps({"reviewer": "SabiLab Reviewer", "confirmed_at": now})),
        )
        conn.commit()
    finally:
        conn.close()
