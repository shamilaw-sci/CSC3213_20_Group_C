-- Run this once in Supabase SQL Editor
-- (Database → SQL Editor → New query → paste → Run)

CREATE OR REPLACE FUNCTION record_inventory_transaction(
    p_item_id         INT,
    p_quantity        INT,
    p_transaction_type TEXT,   -- 'Issue' or 'Return'
    p_transaction_date DATE,
    p_program_id      INT DEFAULT NULL
)
RETURNS inventory_transactions
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_stock INT;
    v_new_stock     INT;
    v_result        inventory_transactions;
BEGIN
    -- Lock the row so concurrent transactions don't double-count stock
    SELECT current_stock
      INTO v_current_stock
      FROM inventory_items
     WHERE id = p_item_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Item % not found', p_item_id;
    END IF;

    -- Calculate new stock based on transaction type
    IF p_transaction_type = 'Issue' THEN
        IF v_current_stock < p_quantity THEN
            RAISE EXCEPTION 'Insufficient stock: have %, need %', v_current_stock, p_quantity;
        END IF;
        v_new_stock := v_current_stock - p_quantity;
    ELSIF p_transaction_type = 'Return' THEN
        v_new_stock := v_current_stock + p_quantity;
    ELSE
        RAISE EXCEPTION 'Invalid transaction_type: %', p_transaction_type;
    END IF;

    -- Update stock atomically (same transaction as the insert below)
    UPDATE inventory_items
       SET current_stock = v_new_stock
     WHERE id = p_item_id;

    -- Log the transaction
    INSERT INTO inventory_transactions
        (item_id, quantity, transaction_type, transaction_date, program_id)
    VALUES
        (p_item_id, p_quantity, p_transaction_type, p_transaction_date, p_program_id)
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$;
