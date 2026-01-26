from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0020_paymentreconciliation_refundrequest_transaction_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE finance_payment
    ADD COLUMN IF NOT EXISTS __uuid_tmp uuid DEFAULT gen_random_uuid() NOT NULL;

ALTER TABLE finance_webhooklog
    ADD COLUMN IF NOT EXISTS __payment_uuid_tmp uuid;

ALTER TABLE finance_refundrequest
    ADD COLUMN IF NOT EXISTS __payment_uuid_tmp uuid;

ALTER TABLE finance_transaction
    ADD COLUMN IF NOT EXISTS __payment_uuid_tmp uuid;

ALTER TABLE finance_paymentauditlog
    ADD COLUMN IF NOT EXISTS __payment_uuid_tmp uuid;

UPDATE finance_webhooklog
SET __payment_uuid_tmp = finance_payment.__uuid_tmp
FROM finance_payment
WHERE finance_webhooklog.payment_id = finance_payment.id;

UPDATE finance_refundrequest
SET __payment_uuid_tmp = finance_payment.__uuid_tmp
FROM finance_payment
WHERE finance_refundrequest.payment_id = finance_payment.id;

UPDATE finance_transaction
SET __payment_uuid_tmp = finance_payment.__uuid_tmp
FROM finance_payment
WHERE finance_transaction.payment_id = finance_payment.id;

UPDATE finance_paymentauditlog
SET __payment_uuid_tmp = finance_payment.__uuid_tmp
FROM finance_payment
WHERE finance_paymentauditlog.payment_id = finance_payment.id;

DO $$
DECLARE
    fk record;
BEGIN
    FOR fk IN
        SELECT conrelid::regclass AS table_name, conname
        FROM pg_constraint
        WHERE confrelid = 'finance_payment'::regclass
          AND contype = 'f'
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', fk.table_name, fk.conname);
    END LOOP;
END$$;

ALTER TABLE finance_payment
    DROP CONSTRAINT IF EXISTS finance_payment_pkey;

ALTER TABLE finance_payment
    RENAME COLUMN id TO __legacy_id;

ALTER TABLE finance_payment
    RENAME COLUMN __uuid_tmp TO id;

ALTER TABLE finance_payment
    ADD CONSTRAINT finance_payment_pkey PRIMARY KEY (id);

ALTER TABLE finance_webhooklog
    RENAME COLUMN payment_id TO __legacy_payment_id;

ALTER TABLE finance_refundrequest
    RENAME COLUMN payment_id TO __legacy_payment_id;

ALTER TABLE finance_transaction
    RENAME COLUMN payment_id TO __legacy_payment_id;

ALTER TABLE finance_paymentauditlog
    RENAME COLUMN payment_id TO __legacy_payment_id;

ALTER TABLE finance_webhooklog
    RENAME COLUMN __payment_uuid_tmp TO payment_id;

ALTER TABLE finance_refundrequest
    RENAME COLUMN __payment_uuid_tmp TO payment_id;

ALTER TABLE finance_transaction
    RENAME COLUMN __payment_uuid_tmp TO payment_id;

ALTER TABLE finance_paymentauditlog
    RENAME COLUMN __payment_uuid_tmp TO payment_id;

ALTER TABLE finance_webhooklog
    ADD CONSTRAINT finance_webhooklog_payment_id_fkey
        FOREIGN KEY (payment_id) REFERENCES finance_payment (id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE finance_refundrequest
    ADD CONSTRAINT finance_refundrequest_payment_id_fkey
        FOREIGN KEY (payment_id) REFERENCES finance_payment (id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE finance_transaction
    ADD CONSTRAINT finance_transaction_payment_id_fkey
        FOREIGN KEY (payment_id) REFERENCES finance_payment (id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE finance_paymentauditlog
    ADD CONSTRAINT finance_paymentauditlog_payment_id_fkey
        FOREIGN KEY (payment_id) REFERENCES finance_payment (id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE finance_webhooklog
    DROP COLUMN IF EXISTS __legacy_payment_id;

ALTER TABLE finance_refundrequest
    DROP COLUMN IF EXISTS __legacy_payment_id;

ALTER TABLE finance_transaction
    DROP COLUMN IF EXISTS __legacy_payment_id;

ALTER TABLE finance_paymentauditlog
    DROP COLUMN IF EXISTS __legacy_payment_id;

ALTER TABLE finance_payment
    DROP COLUMN IF EXISTS __legacy_id;

DROP SEQUENCE IF EXISTS finance_payment_id_seq;
""",
            migrations.RunSQL.noop,
        ),
    ]
