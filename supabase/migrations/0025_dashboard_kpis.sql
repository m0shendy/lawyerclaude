-- 0025: dashboard_kpis materialized view + auto-refresh triggers (T079/T080)
-- All assembly is deterministic — no LLM involved [C-IV].

CREATE MATERIALIZED VIEW IF NOT EXISTS dashboard_kpis AS
SELECT
    (SELECT count(*) FROM cases WHERE stage != 'closed')                                AS open_matters,
    (SELECT count(*) FROM hearings
       WHERE status IN ('scheduled','confirmed')
         AND scheduled_at BETWEEN now() AND now() + INTERVAL '7 days')                 AS upcoming_hearings,
    (SELECT count(*) FROM deadlines
       WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7)                       AS upcoming_deadlines,
    (SELECT count(*) FROM invoices WHERE status IN ('pending','partial'))               AS pending_invoices,
    (SELECT count(*) FROM ai_outputs WHERE review_state = 'draft_unreviewed')          AS pending_review;

-- CONCURRENTLY refresh requires a unique index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_kpis_singleton
    ON dashboard_kpis ((1));

-- Refresh function (T080)
CREATE OR REPLACE FUNCTION refresh_dashboard_kpis()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_kpis;
    RETURN NULL;
END; $$;

DROP TRIGGER IF EXISTS trg_refresh_kpis_cases ON cases;
CREATE TRIGGER trg_refresh_kpis_cases
    AFTER INSERT OR UPDATE OR DELETE ON cases
    FOR EACH STATEMENT EXECUTE FUNCTION refresh_dashboard_kpis();

DROP TRIGGER IF EXISTS trg_refresh_kpis_hearings ON hearings;
CREATE TRIGGER trg_refresh_kpis_hearings
    AFTER INSERT OR UPDATE OR DELETE ON hearings
    FOR EACH STATEMENT EXECUTE FUNCTION refresh_dashboard_kpis();

DROP TRIGGER IF EXISTS trg_refresh_kpis_invoices ON invoices;
CREATE TRIGGER trg_refresh_kpis_invoices
    AFTER INSERT OR UPDATE OR DELETE ON invoices
    FOR EACH STATEMENT EXECUTE FUNCTION refresh_dashboard_kpis();

DROP TRIGGER IF EXISTS trg_refresh_kpis_ai_outputs ON ai_outputs;
CREATE TRIGGER trg_refresh_kpis_ai_outputs
    AFTER INSERT OR UPDATE OR DELETE ON ai_outputs
    FOR EACH STATEMENT EXECUTE FUNCTION refresh_dashboard_kpis();
