-- =====================================================================
-- Pharmenia: Triggers (5) + Cursor-based Procedure (1)
-- Safe re-create: drops then creates the same logic you’re already using
-- =====================================================================

USE pharmenia;

-- ---------------------------------------------------------------------
-- TRIGGER 1: Prevent negative inventory on INSERT
-- Table: inventory_batch
-- Purpose: Enforce business rule that stock can never be negative
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_inv_nonneg_ins;
DELIMITER $$
CREATE TRIGGER trg_inv_nonneg_ins
BEFORE INSERT ON inventory_batch
FOR EACH ROW
BEGIN
  -- If an INSERT tries to create a row with qty_available < 0, block it.
  IF NEW.qty_available < 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Inventory cannot be negative (insert).';
  END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER 2: Prevent negative inventory on UPDATE
-- Table: inventory_batch
-- Purpose: Same rule as above, but for updates to existing rows
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_inv_nonneg_upd;
DELIMITER $$
CREATE TRIGGER trg_inv_nonneg_upd
BEFORE UPDATE ON inventory_batch
FOR EACH ROW
BEGIN
  -- If an UPDATE tries to reduce qty_available below 0, block it.
  IF NEW.qty_available < 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Inventory cannot be negative (update).';
  END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER 3: Validate batch data before insert
-- Table: med_batch
-- Purpose: Ensure clean, valid purchase/batch inputs (dates & amounts)
--          - expiry_date must be on/after purchase_date
--          - purchase_price must be non-negative
--          - gst_percent must be non-negative
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_mb_check_bi;
DELIMITER $$
CREATE TRIGGER trg_mb_check_bi
BEFORE INSERT ON med_batch
FOR EACH ROW
BEGIN
  IF NEW.expiry_date < NEW.purchase_date THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Batch expiry cannot be before purchase date';
  END IF;
  IF NEW.purchase_price < 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Purchase price cannot be negative';
  END IF;
  IF NEW.gst_percent < 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'GST percent cannot be negative';
  END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER 4: Validate invoice item values before insert
-- Table: invoice_item
-- Purpose: Guardrails on sales lines
--          - qty must be positive
--          - unit_price must be non-negative
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_ii_check_bi;
DELIMITER $$
CREATE TRIGGER trg_ii_check_bi
BEFORE INSERT ON invoice_item
FOR EACH ROW
BEGIN
  IF NEW.qty <= 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Invoice item qty must be positive';
  END IF;
  IF NEW.unit_price < 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Invoice item unit_price cannot be negative';
  END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER 5: Clean & validate medicine data before insert
-- Table: medicine
-- Purpose: Keep master data tidy and valid
--          - trim name; ensure not empty
--          - trim salt and HSN; store HSN uppercase
--          - MRP must be non-negative
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_medicine_clean_bi;
DELIMITER $$
CREATE TRIGGER trg_medicine_clean_bi
BEFORE INSERT ON medicine
FOR EACH ROW
BEGIN
  SET NEW.name = TRIM(NEW.name);
  SET NEW.salt = NULLIF(TRIM(NEW.salt), '');
  SET NEW.hsn  = NULLIF(UPPER(TRIM(NEW.hsn)), '');
  IF NEW.name = '' THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT='Medicine name is required';
  END IF;
  IF NEW.mrp < 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT='MRP cannot be negative';
  END IF;
END$$
DELIMITER ;

-- =====================================================================
-- CURSOR-BASED PROCEDURE (1)
-- Name: sp_invoice_create
-- Purpose:
--   Builds an invoice by reading staged lines from invoice_items_temp
--   Uses a CURSOR to iterate those lines; for each medicine, consumes
--   stock FIFO by earliest-expiry batches (non-expired only).
--   Writes invoice header + lines, and decrements inventory, with
--   matching ledger entries.
--
-- How to use from app or SQL:
--   1) TRUNCATE invoice_items_temp;
--   2) INSERT lines into invoice_items_temp(medicine_id, qty);
--   3) CALL sp_invoice_create(<customer_id_or_NULL>, @out_invoice_id);
--   4) SELECT @out_invoice_id;
-- =====================================================================
DROP PROCEDURE IF EXISTS sp_invoice_create;
DELIMITER $$
CREATE PROCEDURE sp_invoice_create(
  IN  p_customer_id BIGINT,
  OUT p_invoice_id  BIGINT
)
BEGIN
  -- Cursor variables
  DECLARE v_med_id     BIGINT;
  DECLARE v_needed     INT;
  DECLARE v_batch_id   BIGINT;
  DECLARE v_take       INT;
  DECLARE v_unit_price DECIMAL(10,2);
  DECLARE done INT DEFAULT 0;

  -- The CURSOR iterates the temp staging table in insertion order
  DECLARE cur CURSOR FOR
    SELECT medicine_id, qty
      FROM invoice_items_temp
     ORDER BY row_id;

  -- When the cursor is exhausted, NOT FOUND sets 'done'
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

  -- Create invoice header (customer can be NULL => Walk-in)
  INSERT INTO invoice(customer_id) VALUES(p_customer_id);
  SET p_invoice_id = LAST_INSERT_ID();

  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO v_med_id, v_needed;
    IF done = 1 THEN LEAVE read_loop; END IF;

    -- Consume requested qty across batches, FIFO by earliest expiry
    WHILE v_needed > 0 DO
      -- Pick earliest non-expired batch with available stock
      SELECT b.batch_id, m.mrp
        INTO v_batch_id, v_unit_price
        FROM med_batch b
        JOIN medicine m        ON m.medicine_id  = b.medicine_id
        JOIN inventory_batch inv ON inv.batch_id = b.batch_id
       WHERE b.medicine_id = v_med_id
         AND b.expiry_date >= CURDATE()
         AND inv.qty_available > 0
       ORDER BY b.expiry_date ASC, b.batch_id ASC
       LIMIT 1;

      -- If none found, abort with clear message
      IF v_batch_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
          SET MESSAGE_TEXT = 'Insufficient stock to fulfill invoice.';
      END IF;

      -- Sell as much as possible from this batch
      SET v_take = LEAST(
        v_needed,
        (SELECT qty_available FROM inventory_batch WHERE batch_id = v_batch_id)
      );

      -- Create the invoice line at the medicine's MRP (unit price)
      INSERT INTO invoice_item(invoice_id, batch_id, qty, unit_price)
      VALUES(p_invoice_id, v_batch_id, v_take, v_unit_price);

      -- Decrement batch inventory and write ledger
      UPDATE inventory_batch
         SET qty_available = qty_available - v_take
       WHERE batch_id = v_batch_id;

      INSERT INTO inventory_ledger(batch_id, ref_type, ref_id, qty_delta)
      VALUES(v_batch_id, 'INVOICE', p_invoice_id, -v_take);

      -- Reduce remaining needed qty and continue
      SET v_needed = v_needed - v_take;
      SET v_batch_id = NULL;
    END WHILE;
  END LOOP;
  CLOSE cur;

  -- Clear staging now that invoice is finalized
  TRUNCATE TABLE invoice_items_temp;
END$$
DELIMITER ;

-- ----------------------
-- Quick verification tips
-- ----------------------
-- SHOW TRIGGERS FROM pharmenia;
-- SHOW CREATE PROCEDURE pharmenia.sp_invoice_create;



------------------------------------------------------------------------------------
-- Sanity Check
------------------------------------------------------------------------------------
-- Count triggers (should be 5)
SELECT COUNT(*) AS trigger_count
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA='pharmenia';

-- List trigger names (should see these 5)
SHOW TRIGGERS FROM pharmenia;
-- Expect:
-- trg_inv_nonneg_ins
-- trg_inv_nonneg_upd
-- trg_mb_check_bi
-- trg_ii_check_bi
-- trg_medicine_clean_bi

-- Confirm the cursor procedure exists
SHOW PROCEDURE STATUS WHERE Db='pharmenia' AND Name='sp_invoice_create';

-- See the body (you'll see DECLARE cur CURSOR ...)
SHOW CREATE PROCEDURE pharmenia.sp_invoice_create;
