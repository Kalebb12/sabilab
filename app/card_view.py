"""Mobile-first HTML template renderer for public Evidence Cards."""

from typing import Any, Dict, Optional

LIMITS_STATEMENT = (
    "Statement of Limits: This Evidence Card reflects simulation performance evaluated automatically by AI. "
    "The AI does not award top-tier Distinguished ratings or predict long-term job success. "
    "Evidence is strictly limited to observed actions and verified quotes within this scenario."
)


def render_card_html(card: Optional[Dict[str, Any]]) -> str:
    """Render a mobile-friendly HTML Evidence Card page without external framework dependencies."""
    if not card:
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SabiLab - Card Unavailable</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #1e293b; padding: 2rem 1rem; text-align: center; }
        .box { max-width: 480px; margin: 3rem auto; background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
        h1 { font-size: 1.25rem; color: #ef4444; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Card Unavailable</h1>
        <p>This Evidence Card has been revoked by the student or does not exist.</p>
    </div>
</body>
</html>"""

    student = card.get("student_name", "Student")
    badge = card.get("badge")
    scores = card.get("scores", [])
    rec = card.get("recommendation", {})

    scores_html = ""
    for s in scores:
        quote_text = f"&ldquo;{s['evidence']}&rdquo;" if s.get("evidence") != "Insufficient evidence" else "<em>Insufficient evidence</em>"
        scores_html += f"""
        <div class="score-card">
            <div class="score-header">
                <strong>{s['criterion']}</strong>
                <span class="badge-pill">{s['level']}</span>
            </div>
            <p class="quote">{quote_text}</p>
            <p class="reason">{s.get('reason', '')}</p>
        </div>"""

    badge_html = ""
    if badge:
        badge_html = f"""
        <div class="badge-box">
            <span class="tier-tag">{badge.get('tier', 'AI-assessed')}</span>
            <h2>{badge.get('name', 'Simulation Badge')}</h2>
            <p>Level: <strong>{badge.get('level', 'Foundation')}</strong></p>
        </div>"""

    comp = card.get("comparison")
    comp_html = ""
    if comp and comp.get("rows"):
        comp_rows = "".join(
            f"<tr><td>{r['criterion']}</td><td><span class='badge-pill'>{r['attempt_1']}</span></td><td><span class='badge-pill'>{r['attempt_2']}</span></td></tr>"
            for r in comp["rows"]
        )
        comp_html = f"""
        <div class="section-title">Attempt Comparison</div>
        <table class="comp-table">
            <thead><tr><th>Criterion</th><th>Attempt 1</th><th>Attempt 2</th></tr></thead>
            <tbody>{comp_rows}</tbody>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>SabiLab Evidence Card - {student}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; color: #0f172a; padding: 1rem; line-height: 1.5; }}
        .container {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.08); padding: 1.5rem; }}
        .header {{ border-bottom: 2px solid #e2e8f0; padding-bottom: 1rem; margin-bottom: 1.25rem; }}
        .brand {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #0284c7; font-weight: 700; }}
        h1 {{ font-size: 1.5rem; color: #0f172a; margin-top: 0.25rem; }}
        .sub {{ font-size: 0.9rem; color: #64748b; }}
        .badge-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 12px; padding: 1rem; margin-bottom: 1.25rem; }}
        .badge-box h2 {{ font-size: 1.1rem; color: #1e40af; margin: 0.25rem 0; }}
        .tier-tag {{ display: inline-block; background: #2563eb; color: white; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; text-transform: uppercase; }}
        .section-title {{ font-size: 1rem; font-weight: 700; color: #334155; margin: 1.25rem 0 0.75rem 0; text-transform: uppercase; letter-spacing: 0.04em; }}
        .score-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.85rem; margin-bottom: 0.75rem; }}
        .score-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; font-size: 0.95rem; }}
        .badge-pill {{ background: #dcfce7; color: #166534; font-size: 0.8rem; font-weight: 600; padding: 2px 8px; border-radius: 12px; }}
        .quote {{ font-style: italic; color: #1e293b; background: #ffffff; border-left: 3px solid #0ea5e9; padding: 0.4rem 0.6rem; font-size: 0.88rem; margin: 0.4rem 0; }}
        .reason {{ font-size: 0.82rem; color: #64748b; }}
        .rec-box {{ background: #fefce8; border: 1px solid #fef08a; border-radius: 10px; padding: 1rem; margin-bottom: 1.25rem; }}
        .rec-box h3 {{ font-size: 0.95rem; color: #854d0e; margin-bottom: 0.35rem; }}
        .rec-box p {{ font-size: 0.85rem; color: #713f12; margin-bottom: 0.25rem; }}
        .comp-table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.25rem; font-size: 0.85rem; }}
        .comp-table th, .comp-table td {{ padding: 6px 8px; border: 1px solid #e2e8f0; text-align: left; }}
        .comp-table th {{ background: #f8fafc; color: #334155; }}
        .limits {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 0.85rem; font-size: 0.78rem; color: #475569; margin-top: 1.5rem; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="brand">SabiLab Verified Evidence Card</span>
            <h1>{student}</h1>
            <p class="sub">Scenario: Adaeze’s Fabrics (Accountant Role)</p>
        </div>
        {badge_html}
        <div class="section-title">Verified Competencies</div>
        {scores_html}
        {comp_html}
        <div class="section-title">Targeted Growth Drill</div>
        <div class="rec-box">
            <h3>{rec.get('area', 'Skill Drill')}</h3>
            <p><strong>Drill:</strong> {rec.get('drill', '')}</p>
            <p><strong>Habit:</strong> {rec.get('habit', '')}</p>
        </div>
        <div class="limits">
            <strong>Notice:</strong> {LIMITS_STATEMENT}
        </div>
    </div>
</body>
</html>"""
