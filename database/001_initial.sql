BEGIN;

CREATE TABLE IF NOT EXISTS customers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer text NOT NULL,
    subject text NOT NULL,
    display_email text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (issuer, subject)
);

CREATE TABLE IF NOT EXISTS claims (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id uuid NOT NULL REFERENCES customers(id),
    name text NOT NULL CHECK (length(trim(name)) > 0),
    sum_insured bigint CHECK (sum_insured > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (customer_id, id)
);

CREATE INDEX IF NOT EXISTS claims_by_customer ON claims (customer_id, id DESC);

CREATE TABLE IF NOT EXISTS claim_documents (
    customer_id uuid NOT NULL,
    claim_id bigint NOT NULL,
    position integer NOT NULL CHECK (position >= 0),
    filename text NOT NULL,
    pdf bytea NOT NULL,
    storage_key text CHECK (storage_key ~ '^[0-9a-f]{32}\.pdf$'),
    content_sha256 text CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (claim_id, position),
    FOREIGN KEY (customer_id, claim_id)
        REFERENCES claims(customer_id, id) ON DELETE CASCADE
);

ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE claims FORCE ROW LEVEL SECURITY;
ALTER TABLE claim_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_documents FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS customer_claims ON claims;
CREATE POLICY customer_claims ON claims
    USING (customer_id = nullif(current_setting('app.customer_id', true), '')::uuid)
    WITH CHECK (customer_id = nullif(current_setting('app.customer_id', true), '')::uuid);

DROP POLICY IF EXISTS customer_documents ON claim_documents;
CREATE POLICY customer_documents ON claim_documents
    USING (customer_id = nullif(current_setting('app.customer_id', true), '')::uuid)
    WITH CHECK (customer_id = nullif(current_setting('app.customer_id', true), '')::uuid);

ALTER TABLE claims ALTER COLUMN customer_id
    SET DEFAULT nullif(current_setting('app.customer_id', true), '')::uuid;
ALTER TABLE claim_documents ALTER COLUMN customer_id
    SET DEFAULT nullif(current_setting('app.customer_id', true), '')::uuid;

CREATE TABLE IF NOT EXISTS claim_estimate_revisions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id uuid NOT NULL DEFAULT nullif(current_setting('app.customer_id', true), '')::uuid,
    claim_id bigint NOT NULL,
    bill_hash text NOT NULL,
    policy_hash text NOT NULL,
    snapshot text NOT NULL,
    saved_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (customer_id, claim_id) REFERENCES claims(customer_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS clinical_review_revisions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id uuid NOT NULL DEFAULT nullif(current_setting('app.customer_id', true), '')::uuid REFERENCES customers(id),
    document_hash text NOT NULL,
    field text NOT NULL,
    previous_value text,
    reviewed_value text,
    extracted_value text,
    source_page integer,
    saved_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bill_row_reviews (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id uuid NOT NULL DEFAULT nullif(current_setting('app.customer_id', true), '')::uuid REFERENCES customers(id),
    document_hash text NOT NULL,
    original text NOT NULL,
    reviewed text NOT NULL,
    saved_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bill_total_reviews (LIKE bill_row_reviews INCLUDING ALL);
ALTER TABLE bill_total_reviews DROP CONSTRAINT IF EXISTS bill_total_reviews_customer_fk;
ALTER TABLE bill_total_reviews ADD CONSTRAINT bill_total_reviews_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(id);

CREATE TABLE IF NOT EXISTS claim_chat_turns (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id uuid NOT NULL DEFAULT nullif(current_setting('app.customer_id', true), '')::uuid,
    claim_id bigint NOT NULL,
    question text NOT NULL,
    answer jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (customer_id, claim_id) REFERENCES claims(customer_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS claim_chat_turns_by_claim ON claim_chat_turns (customer_id, claim_id, id);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['claim_estimate_revisions', 'clinical_review_revisions',
        'bill_row_reviews', 'bill_total_reviews', 'claim_chat_turns']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS customer_records ON %I', table_name);
        EXECUTE format('CREATE POLICY customer_records ON %I USING
            (customer_id = nullif(current_setting(''app.customer_id'', true), '''')::uuid)
            WITH CHECK (customer_id = nullif(current_setting(''app.customer_id'', true), '''')::uuid)', table_name);
    END LOOP;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'claims_app') THEN
        CREATE ROLE claims_app LOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END;
$$;
GRANT USAGE ON SCHEMA public TO claims_app;
GRANT DELETE ON claims TO claims_app;
GRANT SELECT, INSERT ON claims, claim_documents, claim_estimate_revisions,
    clinical_review_revisions, bill_row_reviews, bill_total_reviews, claim_chat_turns TO claims_app;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS password_verifier bytea;
REVOKE UPDATE ON customers FROM claims_app;
GRANT SELECT, INSERT ON customers TO claims_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO claims_app;

COMMIT;
