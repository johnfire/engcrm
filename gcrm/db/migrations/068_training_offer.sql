-- Training belongs alongside Christopher's other offers, in his workspace.
-- Keep any existing Training offer and its settings untouched on reruns.
INSERT INTO offers (workspace_id, slug, name, revenue_kind, sort_order)
SELECT w.id, 'training', 'Training', 'one_off',
       (SELECT COALESCE(MAX(o.sort_order), 0) + 10 FROM offers o WHERE o.workspace_id = w.id)
  FROM workspaces w
 WHERE w.slug = 'default'
ON CONFLICT (workspace_id, slug) DO NOTHING;
