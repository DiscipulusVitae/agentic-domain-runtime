-- =========================================================================
-- LOCAL SUPABASE REVIEWER SMOKE TEST
-- =========================================================================
-- This script performs read-only validations of schemas, tables, RLS, 
-- policies, and seed counts. It does not perform any mutations.
-- =========================================================================

WITH checks AS (
    -- 1. Schemas Existence
    SELECT 
        'Schema existence: core'::text AS check_name,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'core') THEN 'OK' ELSE 'FAILED' END AS status,
        'core schema checked'::text AS details
    UNION ALL
    SELECT 
        'Schema existence: kitchen'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'kitchen') THEN 'OK' ELSE 'FAILED' END,
        'kitchen schema checked'
    UNION ALL
    SELECT 
        'Schema existence: books'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'books') THEN 'OK' ELSE 'FAILED' END,
        'books schema checked'
    UNION ALL
    SELECT 
        'Schema existence: med'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'med') THEN 'OK' ELSE 'FAILED' END,
        'med schema checked'
    UNION ALL
    SELECT 
        'Schema existence: api'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'api') THEN 'OK' ELSE 'FAILED' END,
        'api schema checked'

    -- 2. Key Tables Existence
    UNION ALL
    SELECT 
        'Table existence: core.persons'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'core' AND table_name = 'persons') THEN 'OK' ELSE 'FAILED' END,
        'core.persons table checked'
    UNION ALL
    SELECT 
        'Table existence: core.app_users'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'core' AND table_name = 'app_users') THEN 'OK' ELSE 'FAILED' END,
        'core.app_users table checked'
    UNION ALL
    SELECT 
        'Table existence: kitchen.dishes'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'kitchen' AND table_name = 'dishes') THEN 'OK' ELSE 'FAILED' END,
        'kitchen.dishes table checked'
    UNION ALL
    SELECT 
        'Table existence: books.books'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'books' AND table_name = 'books') THEN 'OK' ELSE 'FAILED' END,
        'books.books table checked'
    UNION ALL
    SELECT 
        'Table existence: med.medical_entries'::text,
        CASE WHEN EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'med' AND table_name = 'medical_entries') THEN 'OK' ELSE 'FAILED' END,
        'med.medical_entries table checked'

    -- 3. Row counts (Seed validation)
    UNION ALL
    SELECT 
        'Seed count: core.persons'::text,
        CASE WHEN (SELECT count(*) FROM "core"."persons") = 2 THEN 'OK' ELSE 'FAILED' END,
        'Found ' || (SELECT count(*) FROM "core"."persons") || ' rows (expected 2)'
    UNION ALL
    SELECT 
        'Seed count: core.app_users'::text,
        CASE WHEN (SELECT count(*) FROM "core"."app_users") = 2 THEN 'OK' ELSE 'FAILED' END,
        'Found ' || (SELECT count(*) FROM "core"."app_users") || ' rows (expected 2)'
    UNION ALL
    SELECT 
        'Seed count: kitchen.dishes'::text,
        CASE WHEN (SELECT count(*) FROM "kitchen"."dishes") = 2 THEN 'OK' ELSE 'FAILED' END,
        'Found ' || (SELECT count(*) FROM "kitchen"."dishes") || ' rows (expected 2)'
    UNION ALL
    SELECT 
        'Seed count: books.books'::text,
        CASE WHEN (SELECT count(*) FROM "books"."books") = 2 THEN 'OK' ELSE 'FAILED' END,
        'Found ' || (SELECT count(*) FROM "books"."books") || ' rows (expected 2)'
    UNION ALL
    SELECT 
        'Seed count: med.medical_entries'::text,
        CASE WHEN (SELECT count(*) FROM "med"."medical_entries") = 3 THEN 'OK' ELSE 'FAILED' END,
        'Found ' || (SELECT count(*) FROM "med"."medical_entries") || ' rows (expected 3)'
    UNION ALL
    SELECT 
        'Seed count: api.token_scopes'::text,
        CASE WHEN (SELECT count(*) FROM "api"."token_scopes") = 2 THEN 'OK' ELSE 'FAILED' END,
        'Found ' || (SELECT count(*) FROM "api"."token_scopes") || ' rows (expected 2)'

    -- 4. RLS Enabled Status
    UNION ALL
    SELECT 
        'RLS active: core.app_users'::text,
        CASE WHEN (SELECT relrowsecurity FROM pg_class WHERE oid = 'core.app_users'::regclass) = true THEN 'OK' ELSE 'FAILED' END,
        'RLS status check'
    UNION ALL
    SELECT 
        'RLS active: kitchen.dishes'::text,
        CASE WHEN (SELECT relrowsecurity FROM pg_class WHERE oid = 'kitchen.dishes'::regclass) = true THEN 'OK' ELSE 'FAILED' END,
        'RLS status check'
    UNION ALL
    SELECT 
        'RLS active: books.books'::text,
        CASE WHEN (SELECT relrowsecurity FROM pg_class WHERE oid = 'books.books'::regclass) = true THEN 'OK' ELSE 'FAILED' END,
        'RLS status check'
    UNION ALL
    SELECT 
        'RLS active: med.medical_entries'::text,
        CASE WHEN (SELECT relrowsecurity FROM pg_class WHERE oid = 'med.medical_entries'::regclass) = true THEN 'OK' ELSE 'FAILED' END,
        'RLS status check'

    -- 5. Policies Existence
    UNION ALL
    SELECT 
        'Policies check: core.app_users (select_own_app_user)'::text,
        CASE WHEN EXISTS(SELECT 1 FROM pg_policies WHERE schemaname = 'core' AND tablename = 'app_users' AND policyname = 'select_own_app_user') THEN 'OK' ELSE 'FAILED' END,
        'policy checked'
    UNION ALL
    SELECT 
        'Policies check: kitchen.dishes (select_all_dishes)'::text,
        CASE WHEN EXISTS(SELECT 1 FROM pg_policies WHERE schemaname = 'kitchen' AND tablename = 'dishes' AND policyname = 'select_all_dishes') THEN 'OK' ELSE 'FAILED' END,
        'policy checked'
    UNION ALL
    SELECT 
        'Policies check: kitchen.dishes (modify_own_dishes)'::text,
        CASE WHEN EXISTS(SELECT 1 FROM pg_policies WHERE schemaname = 'kitchen' AND tablename = 'dishes' AND policyname = 'modify_own_dishes') THEN 'OK' ELSE 'FAILED' END,
        'policy checked'
    UNION ALL
    SELECT 
        'Policies check: books.books (access_all_books)'::text,
        CASE WHEN EXISTS(SELECT 1 FROM pg_policies WHERE schemaname = 'books' AND tablename = 'books' AND policyname = 'access_all_books') THEN 'OK' ELSE 'FAILED' END,
        'policy checked'
    UNION ALL
    SELECT 
        'Policies check: med.medical_entries (access_family_medical_entries)'::text,
        CASE WHEN EXISTS(SELECT 1 FROM pg_policies WHERE schemaname = 'med' AND tablename = 'medical_entries' AND policyname = 'access_family_medical_entries') THEN 'OK' ELSE 'FAILED' END,
        'policy checked'

    -- 6. Auth mapping / Seed Sanity
    UNION ALL
    SELECT 
        'Auth mapping: core.app_users -> auth.users'::text,
        CASE WHEN (
            SELECT count(*) FROM core.app_users au 
            JOIN auth.users u ON au.auth_user_id = u.id
        ) = 2 THEN 'OK' ELSE 'FAILED' END,
        'Mapped ' || (
            SELECT count(*) FROM core.app_users au 
            JOIN auth.users u ON au.auth_user_id = u.id
        ) || ' users to auth.users (expected 2)'
)
SELECT 
    check_name, 
    status, 
    details
FROM checks
WHERE 
    (CASE WHEN status = 'FAILED' THEN 'FAILED_CHECK: ' || check_name ELSE '1' END)::numeric = 1;
