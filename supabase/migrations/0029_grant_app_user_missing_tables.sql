-- 0029: Grant app_user SELECT/INSERT/UPDATE/DELETE on all tables that were
-- missing grants. These tables are referenced by RLS policies (e.g. case_contacts
-- is used in the cases RLS policy), causing InsufficientPrivilegeError on every
-- authenticated request. RLS policies on each table still control row-level access.

GRANT SELECT, INSERT, UPDATE, DELETE ON
    appointments,
    billing_rates,
    case_contacts,
    conflict_check_log,
    contacts,
    correspondence,
    document_checkouts,
    document_folders,
    document_sharing,
    document_templates,
    document_versions,
    hearings,
    invoice_line_items,
    invoices,
    payments,
    portal_access,
    portal_magic_links,
    time_entries
TO app_user;
