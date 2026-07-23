"""Workspace-scoped storage for editable Help Centre content and feedback."""
from gcrm.db.connection import db, serialize_row
from gcrm.tools.db_audit import log_audit


def list_published_help(workspace_id: int | None, language: str, surface: str, query: str = "") -> list[dict]:
    """Return customer-visible articles with a deliberate language fallback."""
    language = "de" if language == "de" else "en"
    title = f"title_{language}"
    summary = f"summary_{language}"
    body = f"body_{language}"
    fallback_title = "title_en" if language == "de" else "title_de"
    fallback_summary = "summary_en" if language == "de" else "summary_de"
    fallback_body = "body_en" if language == "de" else "body_de"
    search = f"%{query.strip()}%"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT id, slug, category, surfaces,
                COALESCE(NULLIF({title}, ''), NULLIF({fallback_title}, ''), slug) AS title,
                COALESCE(NULLIF({summary}, ''), NULLIF({fallback_summary}, ''), '') AS summary,
                COALESCE(NULLIF({body}, ''), NULLIF({fallback_body}, ''), '') AS body
            FROM help_articles
            WHERE workspace_id = COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default'))
              AND status = 'published' AND %s = ANY(surfaces)
              AND (%s = '' OR {title} ILIKE %s OR {summary} ILIKE %s OR {body} ILIKE %s)
            ORDER BY category, title
            """,
            (workspace_id, surface, query.strip(), search, search, search),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def list_help_for_editor(workspace_id: int | None) -> list[dict]:
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM help_articles
            WHERE workspace_id = COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default'))
            ORDER BY category, slug""",
            (workspace_id,),
        )
        return [serialize_row(dict(row)) for row in cur.fetchall()]


def save_help_article(workspace_id: int | None, article: dict) -> int:
    """Create or update one editable article. Publishing is explicit."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO help_articles
                (workspace_id, slug, category, surfaces, status, title_en, title_de,
                 summary_en, summary_de, body_en, body_de, published_at)
            VALUES (COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default')),
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s = 'published' THEN NOW() ELSE NULL END)
            ON CONFLICT (workspace_id, slug) DO UPDATE SET
                category = EXCLUDED.category, surfaces = EXCLUDED.surfaces,
                status = EXCLUDED.status, title_en = EXCLUDED.title_en, title_de = EXCLUDED.title_de,
                summary_en = EXCLUDED.summary_en, summary_de = EXCLUDED.summary_de,
                body_en = EXCLUDED.body_en, body_de = EXCLUDED.body_de,
                published_at = CASE WHEN EXCLUDED.status = 'published' THEN NOW() ELSE help_articles.published_at END,
                updated_at = NOW()
            RETURNING id
            """,
            (workspace_id, article['slug'], article['category'], article['surfaces'], article['status'],
             article['title_en'], article['title_de'], article['summary_en'], article['summary_de'],
             article['body_en'], article['body_de'], article['status']),
        )
        article_id = cur.fetchone()['id']
    log_audit(None, None, 'help.article_saved', f'help_article:{article_id}', article['status'])
    return article_id


def record_help_feedback(workspace_id: int | None, article_id: int, user_id: int | None, helpful: bool, comment: str) -> None:
    with db() as conn:
        conn.cursor().execute(
            """INSERT INTO help_feedback (workspace_id, article_id, user_id, helpful, comment)
            VALUES (COALESCE(%s, (SELECT id FROM workspaces WHERE slug = 'default')), %s, %s, %s, %s)""",
            (workspace_id, article_id, user_id, helpful, comment.strip()[:1000]),
        )
    log_audit(None, None, 'help.feedback_recorded', f'help_article:{article_id}', 'helpful' if helpful else 'not_helpful')


def complete_help_tour(user_id: int) -> None:
    with db() as conn:
        conn.cursor().execute(
            """INSERT INTO help_tour_progress (user_id, tour_key) VALUES (%s, 'core-workflow')
            ON CONFLICT (user_id, tour_key) DO UPDATE SET completed_at = NOW()""",
            (user_id,),
        )
    log_audit(None, None, 'help.tour_completed', f'user:{user_id}', 'core-workflow')


def has_completed_help_tour(user_id: int | None) -> bool:
    if user_id is None:
        return True
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM help_tour_progress WHERE user_id = %s AND tour_key = 'core-workflow'", (user_id,))
        return cur.fetchone() is not None
