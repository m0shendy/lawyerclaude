-- 0027: Client portal — portal_user_id on contacts + portal RLS (T070/T071)

-- T070: portal_user_id column on contacts (client registry)
ALTER TABLE contacts
    ADD COLUMN IF NOT EXISTS portal_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_contacts_portal_user
    ON contacts(portal_user_id) WHERE portal_user_id IS NOT NULL;

-- T071: portal RLS policies
-- cases: client sees only cases where they appear as a contact (case_contacts join)
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cases_portal_client ON cases;
CREATE POLICY cases_portal_client ON cases
    FOR SELECT
    USING (
        -- internal users always allowed (they set request.jwt.claims role)
        (current_setting('request.jwt.claims', true)::json->>'role') != 'client'
        OR
        id IN (
            SELECT case_id FROM case_contacts cc
            JOIN contacts c ON c.id = cc.contact_id
            WHERE c.portal_user_id = auth.uid()
        )
    );

-- documents: client sees only non-confidential shared documents
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS documents_portal_client ON documents;
CREATE POLICY documents_portal_client ON documents
    FOR SELECT
    USING (
        (current_setting('request.jwt.claims', true)::json->>'role') != 'client'
        OR
        id IN (
            SELECT ds.document_id FROM document_sharing ds
            JOIN contacts c ON c.id = ds.shared_with_contact_id
            WHERE c.portal_user_id = auth.uid()
        )
    );

-- invoices: client sees own invoices via contact join
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS invoices_portal_client ON invoices;
CREATE POLICY invoices_portal_client ON invoices
    FOR SELECT
    USING (
        (current_setting('request.jwt.claims', true)::json->>'role') != 'client'
        OR
        client_contact_id IN (
            SELECT id FROM contacts WHERE portal_user_id = auth.uid()
        )
    );

-- appointments: client sees own appointments
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS appointments_portal_client ON appointments;
CREATE POLICY appointments_portal_client ON appointments
    FOR SELECT
    USING (
        (current_setting('request.jwt.claims', true)::json->>'role') != 'client'
        OR
        client_contact_id IN (
            SELECT id FROM contacts WHERE portal_user_id = auth.uid()
        )
    );

-- ai_outputs: client sees ONLY approved outputs linked to their matters [C-II]
ALTER TABLE ai_outputs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_outputs_portal_client ON ai_outputs;
CREATE POLICY ai_outputs_portal_client ON ai_outputs
    FOR SELECT
    USING (
        (current_setting('request.jwt.claims', true)::json->>'role') != 'client'
        OR
        (
            review_state = 'approved'
            AND case_id IN (
                SELECT case_id FROM case_contacts cc
                JOIN contacts c ON c.id = cc.contact_id
                WHERE c.portal_user_id = auth.uid()
            )
        )
    );
