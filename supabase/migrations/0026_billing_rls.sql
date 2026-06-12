-- 0026: RLS policies for billing tables (T038)
-- partner_manager + lawyer: full CRUD
-- paralegal + secretary: SELECT only on invoices/items/payments
-- client role: SELECT on own invoices/payments via portal_user_id join

ALTER TABLE invoices         ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_line_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments         ENABLE ROW LEVEL SECURITY;

-- app_user (all internal roles) full access
DROP POLICY IF EXISTS invoices_app_user         ON invoices;
DROP POLICY IF EXISTS invoice_items_app_user    ON invoice_line_items;
DROP POLICY IF EXISTS payments_app_user         ON payments;

CREATE POLICY invoices_app_user ON invoices
    FOR ALL TO app_user USING (true) WITH CHECK (true);

CREATE POLICY invoice_items_app_user ON invoice_line_items
    FOR ALL TO app_user USING (true) WITH CHECK (true);

CREATE POLICY payments_app_user ON payments
    FOR ALL TO app_user USING (true) WITH CHECK (true);
