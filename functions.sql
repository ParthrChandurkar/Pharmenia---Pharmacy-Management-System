-- =========================================================
-- FUNCTIONS (3)
-- =========================================================

-- 1) Current stock available for a medicine (used by UI/search)
DROP FUNCTION IF EXISTS fn_stock_available;
DELIMITER $$
CREATE FUNCTION fn_stock_available(p_medicine_id BIGINT)
RETURNS INT
DETERMINISTIC
BEGIN
  DECLARE v INT;
  SELECT COALESCE(SUM(inv.qty_available),0)
    INTO v
    FROM inventory_batch inv
    JOIN med_batch b ON b.batch_id = inv.batch_id
   WHERE b.medicine_id = p_medicine_id;
  RETURN COALESCE(v,0);
END$$
DELIMITER ;

-- 2) Is a batch near expiry within N days? (1=yes, 0=no)
DROP FUNCTION IF EXISTS fn_is_near_expiry;
DELIMITER $$
CREATE FUNCTION fn_is_near_expiry(p_batch_id BIGINT, p_days INT)
RETURNS TINYINT
DETERMINISTIC
BEGIN
  DECLARE v_exp DATE;
  SELECT expiry_date INTO v_exp FROM med_batch WHERE batch_id = p_batch_id;
  IF v_exp IS NULL THEN
    RETURN 0;
  END IF;
  IF v_exp BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL p_days DAY) THEN
    RETURN 1;
  END IF;
  RETURN 0;
END$$
DELIMITER ;

-- 3) Total invoice amount (sum of qty * unit_price)
DROP FUNCTION IF EXISTS fn_invoice_total;
DELIMITER $$
CREATE FUNCTION fn_invoice_total(p_invoice_id BIGINT)
RETURNS DECIMAL(12,2)
DETERMINISTIC
BEGIN
  DECLARE v DECIMAL(12,2);
  SELECT COALESCE(SUM(ii.qty * ii.unit_price),0.00)
    INTO v
    FROM invoice_item ii
   WHERE ii.invoice_id = p_invoice_id;
  RETURN v;
END$$
DELIMITER ;
