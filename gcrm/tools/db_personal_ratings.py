"""The private per-user ratings shared by organizations and people.

One row per (user, organization) in contact_user_priorities and per
(user, person) in person_user_priorities holds that user's priority plus the
short- and long-term value ratings. Each rating is set or cleared on its own;
a row whose last rating is cleared is deleted."""

# Rating name -> the values it accepts. Priority runs 1 (best) to 6 (forget it)
# on organizations; a person's contact-value rating, stored as priority, is
# held to 1-5 by set_person_value_rating. The two values run 0 (zero) to 3 (high).
RATING_RANGES = {
    "priority": range(1, 7),
    "short_term_value": range(0, 4),
    "long_term_value": range(0, 4),
}

# URL segment -> rating name, for the routes that set the two value ratings.
VALUE_HORIZONS = {
    "short-term": "short_term_value",
    "long-term": "long_term_value",
}

# Table -> the column naming the rated record. Both are trusted into SQL below.
_TARGET_COLUMNS = {
    "contact_user_priorities": "contact_id",
    "person_user_priorities": "person_id",
}


def check_rating(rating: str, value: int | None) -> None:
    """Raise ValueError for an unknown rating or an out-of-range value."""
    if rating not in RATING_RANGES:
        raise ValueError(f"Unknown rating: {rating}")
    allowed = RATING_RANGES[rating]
    if value is not None and value not in allowed:
        raise ValueError(f"{rating} must be between {allowed.start} and {allowed.stop - 1}")


def store_rating(
    cur, table: str, user_id: int, workspace_id: int, target_id: int, rating: str, value: int | None,
) -> int | None:
    """Set or clear one rating on the caller's open cursor; return the stored value.

    The caller has already checked the target exists in the user's workspace."""
    check_rating(rating, value)
    target = _TARGET_COLUMNS[table]
    key = (user_id, workspace_id, target_id)
    if value is None:
        # Drop the row if this was its only rating, otherwise just blank the one column.
        others_empty = " AND ".join(f"{other} IS NULL" for other in RATING_RANGES if other != rating)
        cur.execute(
            f"DELETE FROM {table} WHERE user_id = %s AND workspace_id = %s AND {target} = %s "
            f"AND {others_empty}",
            key,
        )
        cur.execute(
            f"UPDATE {table} SET {rating} = NULL, updated_at = NOW() "
            f"WHERE user_id = %s AND workspace_id = %s AND {target} = %s",
            key,
        )
        return None

    cur.execute(
        f"""
        INSERT INTO {table} (workspace_id, user_id, {target}, {rating})
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, {target})
        DO UPDATE SET
            {rating} = EXCLUDED.{rating},
            workspace_id = EXCLUDED.workspace_id,
            updated_at = NOW()
        RETURNING {rating}
        """,
        (workspace_id, user_id, target_id, value),
    )
    return cur.fetchone()[rating]
