"""Rules routes — list, detail, toggle, create."""

from __future__ import annotations

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse

from mailsort.classifier.rules import RuleEngine

router = APIRouter(prefix="/rules")

@router.get("/audit/{audit_id}/explain")
def explain_move(request: Request, audit_id: int):
    db = request.state.db
    templates = request.app.state.templates

    # Fetch the specific audit log entry
    audit = db.execute("SELECT * FROM audit_log WHERE id = ?", (audit_id,)).fetchone()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    explanation = ""
    stats = None

    if audit["classification_source"] == "rule" and audit["rule_id"]:
        # Fetch rule and calculate performance
        rule = db.execute("SELECT * FROM rules WHERE id = ?", (audit["rule_id"],)).fetchone()
        if rule:
            engine = RuleEngine(db, request.app.state.config.classification.thresholds)
            stats = engine.get_rule_performance(rule["id"], sample_size=50)
            
            explanation = (
                f"This was moved to {audit['target_folder']} because it matched the "
                f"{rule['rule_type']} rule for {rule['condition_value']}, which has a "
                f"{stats['success_rate']:.0f}% success rate over the last {stats['total']} emails."
            )
    elif audit["classification_source"] == "llm":
        explanation = f"This was moved via AI analysis. Reasoning: {audit['llm_reasoning']}"
    elif audit["classification_source"] == "thread":
        explanation = "This was moved because another email in this conversation was already sorted to this folder."
    else:
        explanation = "No automatic classification was applied to this email."

    return templates.TemplateResponse("audit/explain.html", {
        "request": request,
        "audit": audit,
        "explanation": explanation,
        "stats": stats,
    })

@router.get("/")
def rules_list(
    request: Request,
    filter: str = "active",
    type: str = "",
    search: str = "",
    folder: str = "",
    conf_min: str = "",
    conf_max: str = "",
):
    db = request.state.db
    templates = request.app.state.templates

    conditions: list[str] = []
    params: list = []

    # Tab filter
    if filter == "inactive":
        conditions.append("active = 0")
    elif filter == "suggested":
        conditions.append("active = 0 AND source = 'llm_suggested'")
    elif filter == "all":
        pass  # no active filter
    else:
        conditions.append("active = 1")

    # Search filters
    if type:
        conditions.append("rule_type = ?")
        params.append(type)
    if search:
        conditions.append("condition_value LIKE ?")
        params.append(f"%{search}%")
    if folder:
        conditions.append("target_folder_path LIKE ?")
        params.append(f"%{folder}%")
    if conf_min:
        try:
            conditions.append("confidence >= ?")
            params.append(float(conf_min))
        except ValueError:
            pass
    if conf_max:
        try:
            conditions.append("confidence < ?")
            params.append(float(conf_max))
        except ValueError:
            pass

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rules = db.execute(
        f"SELECT * FROM rules {where} ORDER BY rule_type, condition_value",
        tuple(params),
    ).fetchall()

    # Counts for tabs (unaffected by search filters)
    count_active = db.execute("SELECT COUNT(*) FROM rules WHERE active = 1").fetchone()[0]
    count_inactive = db.execute("SELECT COUNT(*) FROM rules WHERE active = 0").fetchone()[0]
    count_suggested = db.execute(
        "SELECT COUNT(*) FROM rules WHERE active = 0 AND source = 'llm_suggested'"
    ).fetchone()[0]
    count_all = count_active + count_inactive

    # Distinct folders for filter dropdown
    folders = db.execute(
        "SELECT DISTINCT target_folder_path FROM rules ORDER BY target_folder_path"
    ).fetchall()

    return templates.TemplateResponse("rules/list.html", {
        "request": request,
        "rules": rules,
        "filter": filter,
        "counts": {
            "active": count_active,
            "inactive": count_inactive,
            "suggested": count_suggested,
            "all": count_all,
        },
        "filters": {
            "type": type,
            "search": search,
            "folder": folder,
            "conf_min": conf_min,
            "conf_max": conf_max,
        },
        "folders": [r["target_folder_path"] for r in folders],
        "nav_active": "rules",
    })


@router.get("/{rule_id}")
def rule_detail(request: Request, rule_id: int):
    db = request.state.db
    templates = request.app.state.templates

    rule = db.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    if not rule:
        return templates.TemplateResponse("rules/detail.html", {
            "request": request,
            "rule": None,
            "audit_rows": [],
            "nav_active": "rules",
        })

    # Recent audit log entries that matched this rule
    audit_rows = db.execute(
        "SELECT * FROM audit_log WHERE rule_id = ? ORDER BY created_at DESC LIMIT 50",
        (rule_id,),
    ).fetchall()

    # Coherence stats and evidence emails for this rule's condition
    evidence_rows = []
    if rule["rule_type"] in ("exact_sender", "list_id", "sender_domain"):
        col = {
            "exact_sender": "from_address",
            "sender_domain": "from_domain",
            "list_id": "list_id",
        }[rule["rule_type"]]

        cond_val = rule["condition_value"]

        to_target = db.execute(
            f"SELECT COUNT(*) FROM audit_log WHERE {col} COLLATE NOCASE = ? AND target_folder = ? AND moved = 1",
            (cond_val, rule["target_folder_path"]),
        ).fetchone()[0]
        total = db.execute(
            f"SELECT COUNT(*) FROM audit_log WHERE {col} COLLATE NOCASE = ? AND moved = 1",
            (cond_val,),
        ).fetchone()[0]
        coherence = to_target / total * 100 if total > 0 else 0

        # All emails matching this condition (evidence for why the rule exists)
        evidence_rows = db.execute(
            f"SELECT * FROM audit_log WHERE {col} COLLATE NOCASE = ? ORDER BY created_at DESC LIMIT 100",
            (cond_val,),
        ).fetchall()
    else:
        to_target = 0
        total = 0
        coherence = 0

    return templates.TemplateResponse("rules/detail.html", {
        "request": request,
        "rule": rule,
        "audit_rows": audit_rows,
        "evidence_rows": evidence_rows,
        "coherence": coherence,
        "evidence_count": to_target,
        "evidence_total": total,
        "nav_active": "rules",
    })


@router.post("/{rule_id}/toggle")
def toggle_rule(request: Request, rule_id: int):
    db = request.state.db
    rule = db.execute("SELECT active FROM rules WHERE id = ?", (rule_id,)).fetchone()
    if rule:
        new_active = 0 if rule["active"] else 1
        db.execute(
            "UPDATE rules SET active = ?, updated_at = datetime('now') WHERE id = ?",
            (new_active, rule_id),
        )
        db.commit()
    return RedirectResponse(url=f"/rules/{rule_id}", status_code=303)


@router.post("/create")
def create_rule(
    request: Request,
    rule_type: str = Form(...),
    condition_value: str = Form(...),
    target_folder_path: str = Form(...),
    confidence: float = Form(0.90),
):
    db = request.state.db
    db.execute(
        "INSERT INTO rules (rule_type, condition_value, target_folder_path, "
        "confidence, source, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'manual', datetime('now'), datetime('now'))",
        (rule_type, condition_value, target_folder_path, confidence),
    )
    db.commit()
    return RedirectResponse(url="/rules", status_code=303)
