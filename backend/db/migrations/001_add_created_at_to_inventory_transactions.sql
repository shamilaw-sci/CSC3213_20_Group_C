-- Migration: Add created_at timestamp to inventory_transactions
-- This migration adds a creation timestamp to track when each transaction was recorded.

ALTER TABLE IF EXISTS inventory_transactions
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now());

-- For existing records that don't have created_at yet, set it to transaction_date at midnight UTC
UPDATE inventory_transactions
SET created_at = (transaction_date AT TIME ZONE 'utc')::timestamp with time zone
WHERE created_at IS NULL;

-- Make the column NOT NULL after backfill
ALTER TABLE inventory_transactions
ALTER COLUMN created_at SET NOT NULL;
