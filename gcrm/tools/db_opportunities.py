"""Persist and retrieve explainable custom-AI opportunity assessments."""

import json

from psycopg2.extras import Json

from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit


def get_organizations_needing_opportunity_analysis(limit: int = 50) -> list[dict]:
    """Return active contacts without a current opportunity assessment."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.*
            FROM contacts c
            WHERE c.deleted_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM ai_analysis analysis
                  WHERE analysis.contact_id = c.id
                    AND analysis.deleted_at IS NULL
                    AND analysis.analysis_kind = 'opportunity'
              )
            ORDER BY c.starred DESC, c.fit_score DESC NULLS LAST, c.created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [serialize_row(dict(row)) for row in cursor.fetchall()]


def get_latest_opportunity_analysis(contact_id: int) -> dict | None:
    """Return the current opportunity assessment for a contact, if one exists."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM ai_analysis
            WHERE contact_id = %s AND deleted_at IS NULL AND analysis_kind = 'opportunity'
            ORDER BY analysis_date DESC, id DESC
            LIMIT 1
            """,
            (contact_id,),
        )
        row = cursor.fetchone()
    return _deserialize_json_fields(dict(row)) if row else None


def _deserialize_json_fields(analysis: dict) -> dict:
    for field in ("evidence", "recommended_services", "discovery_questions"):
        if isinstance(analysis.get(field), str):
            analysis[field] = json.loads(analysis[field])
    return analysis


def save_opportunity_analysis(contact_id: int, analysis: dict, model_used: str) -> None:
    """Save one transparent opportunity assessment for a contact."""
    with db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ai_analysis (
                contact_id, analysis_kind, model_used, fit_reasoning, suggested_approach,
                priority_score, opportunity_score, confidence_score, evidence,
                recommended_services, discovery_questions, raw_response
            ) VALUES (%s, 'opportunity', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                contact_id,
                model_used,
                analysis["fit_reasoning"],
                analysis["suggested_approach"],
                analysis["priority_score"],
                analysis["opportunity_score"],
                analysis["confidence_score"],
                Json(analysis["evidence"]),
                Json(analysis["recommended_services"]),
                Json(analysis["discovery_questions"]),
                json.dumps(analysis, ensure_ascii=False),
            ),
        )
    log_audit(
        None,
        None,
        "contact.opportunity_analyzed",
        f"contact:{contact_id}",
        str(analysis["opportunity_score"]),
    )
