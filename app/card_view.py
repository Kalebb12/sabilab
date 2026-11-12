"""Mobile-first HTML renderer for public Evidence Cards matching SabiLab design."""

import html
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.card import normalize_visible_fields
from app.rubric import (
    get_criteria_map,
    get_level_display,
    is_valid_criterion,
    is_valid_level,
    normalize_level,
    normalize_criterion_id,
)

STYLE = (
    "@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Public+Sans:wght@400;500;600&display=swap');\n"
    ":root{color-scheme:light;--ink:#1B1A4B;--ink2:#2A2870;--page:#F6F5FB;--card:#fff;--line:#E3E1F0;--text:#25244A;--mute:#5E5C82;--violet:#6D4AFF;--violet-soft:#EAE5FF;--go:#1B8A4E;--go-d:#146B3B;--red:#E5484D;--sun:#F5A524;--teal:#1F5A63;--display:'Bricolage Grotesque','Segoe UI',system-ui,sans-serif;--body:'Public Sans','Segoe UI',system-ui,sans-serif}\n"
    "*{box-sizing:border-box}body{margin:0;padding:clamp(16px,4vw,48px);font:400 16px/1.6 var(--body);color:var(--text);background:var(--page)}\n"
    ".card{width:min(100%,760px);margin:0 auto;overflow:hidden;border:1px solid var(--line);border-radius:20px;background:var(--card);box-shadow:0 24px 50px -30px rgba(27,26,75,.4)}\n"
    ".header{padding:clamp(22px,5vw,36px);background:var(--ink);color:#fff}.header-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:22px}\n"
    ".brand{color:#B9B7E6;font:800 14px var(--display);letter-spacing:.09em;text-transform:uppercase}.tier{display:inline-block;padding:5px 12px;border-radius:999px;background:var(--violet);color:#fff;font-size:12px;font-weight:600}\n"
    ".s-row{display:flex;align-items:center;gap:16px}.avatar{display:grid;width:54px;height:54px;flex:none;place-items:center;border:2px solid #B9B7E6;border-radius:50%;background:#302d67;color:#fff;font:700 19px var(--display)}\n"
    "h1,h2,h3{font-family:var(--display);color:var(--ink);line-height:1.08;letter-spacing:-.02em}h1{color:#fff;font-size:clamp(25px,5vw,36px);font-weight:800}.sub{margin:7px 0 0;color:#B9B7E6;font-size:14px}\n"
    ".strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:16px;border-bottom:1px solid var(--line);background:#fff;text-align:center}.s-box{padding:10px 4px;border:1px solid var(--line);border-radius:12px;background:var(--page)}\n"
    ".s-box span{display:block;color:var(--mute);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}.s-box strong{display:block;margin-top:3px;color:var(--ink);font:800 22px var(--display)}\n"
    ".body{padding:clamp(20px,5vw,36px)}.sec-title{margin:24px 0 12px;color:var(--mute);font:800 13px var(--display);letter-spacing:.1em;text-transform:uppercase}\n"
    ".dimension{margin:0 0 24px}.criterion-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.crit-row{min-width:0;padding:16px;border:1px solid rgba(104,72,199,.13);border-radius:16px;background:#fff;box-shadow:0 12px 32px rgba(32,29,75,.06)}\n"
    ".crit-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:10px}.crit-name{color:var(--ink);font:700 17px var(--display)}\n"
    ".pill{flex:none;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600}.pill-proficient{background:#DDF3E6;color:#145C34}.pill-foundation{background:#FDE7E7;color:#9B2226}.pill-needs_practice{background:#FCEBEA;color:#9B2226}.pill-insufficient_evidence{background:var(--violet-soft);color:var(--ink2)}\n"
    ".meter{display:flex;gap:4px;margin:6px 0 12px}.bar{height:6px;flex:1;border-radius:99px;background:var(--line)}.bar.np{background:var(--red)}.bar.f{background:var(--sun)}.bar.p{background:var(--go)}\n"
    ".quote{margin:10px 0 0;padding:11px 14px;border-left:4px solid var(--violet);border-radius:0 10px 10px 0;background:var(--violet-soft);color:var(--ink2);font-size:14px;font-style:italic;overflow-wrap:anywhere}.reason{margin:9px 0 0;color:var(--mute);font-size:13px}\n"
    ".insufficient-group{margin-top:12px;padding:12px 14px;border:1px dashed #C7C2DF;border-radius:12px;background:var(--page);color:var(--mute);font-size:14px}.insufficient-group summary{color:var(--ink2);font-weight:600;cursor:pointer}.insufficient-group ul{margin:10px 0 0;padding-left:22px}\n"
    ".calm-banner{margin:8px 0 24px;padding:24px;border:1px solid #D5CEFA;border-radius:16px;background:var(--violet-soft);color:var(--ink2);text-align:left}.calm-banner h2{margin-bottom:8px;font-size:22px}.calm-banner p{font-size:15px}\n"
    ".badge-box,.drill-box{margin-top:20px;padding:20px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:0 12px 32px rgba(32,29,75,.06)}.badge-box h2,.drill-box h2{margin-bottom:8px;font-size:21px}.badge-level{display:inline-block;margin-top:8px;padding:5px 12px;border-radius:999px;background:var(--go);color:#fff;font-size:13px;font-weight:600}.drill-box p{margin:8px 0 0;font-size:14px}\n"
    ".limits{margin-top:24px;padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--page);color:var(--mute);font-size:13px}.limits strong{color:var(--ink)}\n"
    ".comp-table{width:100%;margin:12px 0 20px;border-collapse:collapse;font-size:13px}.comp-table th,.comp-table td{padding:9px;border:1px solid var(--line);text-align:left}.comp-table th{background:var(--page);color:var(--mute)}\n"
    ".footer{display:flex;justify-content:space-between;gap:12px;padding:16px 24px;border-top:1px solid var(--line);color:#8B87A8;font-size:12px}\n"
    "@media(max-width:600px){body{padding:12px}.strip{grid-template-columns:repeat(2,minmax(0,1fr))}.criterion-grid{grid-template-columns:1fr}.footer{flex-direction:column}.s-row{align-items:flex-start}}\n"
)


def _fmt_date(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "12 Nov 2026"
    try:
        return datetime.fromisoformat(iso_str).strftime("%d %b %Y")
    except Exception:
        return "12 Nov 2026"


def _initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "SL"
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()


def _render_outdated(slug: str, student: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Evidence Card</title><style>{STYLE}</style></head>
<body><div class="card"><div class="header"><div class="header-top"><span class="brand">Evidence Card</span></div><h1>{student}</h1></div>
<div class="body"><div class="calm-banner">Outdated result, please retake the scenario.<br><span style="font-size:0.82rem;font-weight:400;color:#6A668D">This session was scored under an earlier rubric version.</span></div></div>
<div class="footer"><span>Card ID: {html.escape(slug[:8])}</span><span>SabiLab</span></div></div></body></html>"""


def render_card_html(card: Optional[Dict[str, Any]]) -> str:
    if not card:
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Card Unavailable</title><style>{STYLE}</style></head><body><div class="card"><div class="body" style="text-align:center;padding:3rem 1rem"><h2>Card Unavailable</h2><p style="color:#6A668D;margin-top:0.5rem">This card has been revoked or does not exist.</p></div></div></body></html>"""
    slug = card.get("slug", "")
    raw_student = card.get("student_name") or "SabiLab learner"
    student = html.escape(raw_student)
    s_role = card.get("student_role") or "Accounts Assistant"
    s_title = card.get("scenario_title") or "Adaeze's Fabrics"
    sub_title = html.escape(f"{s_role}, {s_title}")
    vis = set(normalize_visible_fields(card.get("visible_fields")))
    scores = card.get("scores", []) if "scores" in vis else []
    for s in scores:
        if not is_valid_criterion(s.get("criterion", "")) or not is_valid_level(s.get("level", "")):
            return _render_outdated(slug, student)

    c_map = get_criteria_map()
    counts = {"proficient": 0, "foundation": 0, "needs_practice": 0, "insufficient_evidence": 0}
    by_dim: Dict[str, List[Dict[str, Any]]] = {}
    for s in scores:
        lvl = normalize_level(s.get("level", "")) or "insufficient_evidence"
        counts[lvl] = counts.get(lvl, 0) + 1
        cid = normalize_criterion_id(s.get("criterion", "")) or s.get("criterion", "")
        dim = c_map.get(cid, {}).get("dimension", s.get("dimension", "Accounts"))
        by_dim.setdefault(dim, []).append({**s, "canon_level": lvl, "name": c_map.get(cid, {}).get("name", cid)})

    all_insufficient = len(scores) > 0 and counts["insufficient_evidence"] == len(scores)
    tier_label = "Human-verified" if card.get("routing") == "Human-verified" else "AI-assessed"
    tier_html = f'<span class="tier">{tier_label}</span>' if "verification_tier" in vis else ""
    card_date = _fmt_date(card.get("published_time"))

    comp_html = ""
    if "scores" in vis:
        if all_insufficient:
            comp_html = (
                '<section class="calm-banner"><h2>Not enough evidence from this shift</h2>'
                '<p>The messages in this simulation did not provide enough verified evidence '
                'to assign competency levels. No level is shown for this attempt.</p></section>'
            )
        else:
            for dim, d_scores in by_dim.items():
                active = [s for s in d_scores if s["canon_level"] != "insufficient_evidence"]
                in_ev = [s for s in d_scores if s["canon_level"] == "insufficient_evidence"]
                rows = ""
                for s in active:
                    lvl = s["canon_level"]
                    m = f'<div class="meter"><div class="bar np"></div><div class="bar {"f" if lvl in ("foundation","proficient") else ""}"></div><div class="bar {"p" if lvl=="proficient" else ""}"></div></div>'
                    q = f'<p class="quote">&ldquo;{html.escape(s["evidence"])}&rdquo;</p>' if ("quotes" in vis and s.get("evidence")) else ""
                    r = f'<p class="reason">{html.escape(s.get("reason",""))}</p>' if s.get("reason") else ""
                    rows += f'<div class="crit-row"><div class="crit-head"><span class="crit-name">{html.escape(s["name"])}</span><span class="pill pill-{lvl}">{get_level_display(lvl)}</span></div>{m}{q}{r}</div>'
                insufficient_names = "".join(
                    "<li>" + html.escape(s["name"]) + "</li>" for s in in_ev
                )
                coll = (
                    f'<details class="insufficient-group"><summary>Not enough evidence '
                    f'({len(in_ev)} criteria)</summary><ul>{insufficient_names}</ul></details>'
                    if in_ev else ""
                )
                comp_html += f'<section class="dimension"><div class="sec-title">{html.escape(dim)}</div><div class="criterion-grid">{rows}</div>{coll}</section>'

    comp = card.get("comparison")
    if "scores" in vis and comp and comp.get("rows"):
        c_rows = "".join(
            f"<tr><td>{html.escape(r['criterion'])}</td><td><span class='pill pill-{normalize_level(r['attempt_1'])}'>{html.escape(get_level_display(r['attempt_1']))}</span></td><td><span class='pill pill-{normalize_level(r['attempt_2'])}'>{html.escape(get_level_display(r['attempt_2']))}</span></td></tr>"
            for r in comp["rows"]
        )
        comp_html += f'<div class="sec-title">Attempt Comparison</div><table class="comp-table"><thead><tr><th>Criterion</th><th>Attempt 1</th><th>Attempt 2</th></tr></thead><tbody>{c_rows}</tbody></table>'

    strip_html = ""
    if "scores" in vis and scores and not all_insufficient:
        strip_html = f'<div class="strip"><div class="s-box"><span>Proficient</span><strong>{counts["proficient"]}</strong></div><div class="s-box"><span>Foundation</span><strong>{counts["foundation"]}</strong></div><div class="s-box"><span>Needs Practice</span><strong>{counts["needs_practice"]}</strong></div><div class="s-box"><span>Not Enough</span><strong>{counts["insufficient_evidence"]}</strong></div></div>'

    drill_html = ""
    rec = card.get("recommendation") or {}
    if "growth_drill" in vis and rec.get("area"):
        drill_html = f'<section class="drill-box"><h2>Targeted Growth Drill</h2><strong>{html.escape(rec.get("area",""))}</strong><p><strong>Drill:</strong> {html.escape(rec.get("drill",""))}</p><p><strong>Habit:</strong> {html.escape(rec.get("habit",""))}</p></section>'

    badge_html = ""
    badge = card.get("badge")
    if "badges" in vis and badge:
        badge_html = (
            f'<section class="badge-box"><h2>Simulation Badge</h2>'
            f'<p>{html.escape(badge.get("name", "SabiLab Simulation"))}</p>'
            f'<span class="badge-level">{html.escape(badge.get("level", "Foundation"))}</span></section>'
        )

    human_note = ""
    if tier_label == "Human-verified" and "verification_tier" in vis:
        rev = card.get("reviewer_info") or {}
        human_note = f' A reviewer confirmed this result with {html.escape(rev.get("reviewer", "SabiLab Reviewer"))} on {_fmt_date(rev.get("time"))}.'
    limits_text = (
        "This card shows one simulated shift, scored by AI against a published rubric. "
        "AI scores can be wrong. The highest level an AI can award is Proficient. "
        "Evidence is limited to observed messages and verified quotes. It does not predict job performance."
        f"{human_note}"
    )
    avatar_html = f'<div class="avatar" aria-hidden="true">{html.escape(_initials(raw_student))}</div>' if "name" in vis else ""

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Evidence Card - {student}</title><style>{STYLE}</style></head>
<body><div class="card"><div class="header"><div class="header-top"><span class="brand">Evidence Card</span>{tier_html}</div><div class="s-row">{avatar_html}<div><h1>{student}</h1><p class="sub">{sub_title} &bull; {card_date}</p></div></div></div>
{strip_html}<div class="body">{badge_html}{comp_html}{drill_html}<div class="limits"><strong>Limits Notice:</strong> {limits_text}</div></div>
<div class="footer"><span>Card ID: {html.escape(slug[:8])}</span><span>SabiLab Workplace Simulation</span></div></div></body></html>"""
