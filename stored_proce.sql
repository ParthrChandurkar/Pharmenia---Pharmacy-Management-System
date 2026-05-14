-- =========================================================
-- STORED PROCEDURES (3)
-- =========================================================

-- 1) Sales summary between two datetimes (units + revenue by medicine)
DROP PROCEDURE IF EXISTS sp_sales_summary;
DELIMITER $$
CREATE PROCEDURE sp_sales_summary(IN p_from DATETIME, IN p_to DATETIME)
BEGIN
  SELECT
    m.medicine_id,
    m.name,
    SUM(ii.qty) AS units_sold,
    SUM(ii.qty * ii.unit_price) AS revenue
  FROM invoice i
  JOIN invoice_item ii ON ii.invoice_id = i.invoice_id
  JOIN med_batch b     ON b.batch_id    = ii.batch_id
  JOIN medicine m      ON m.medicine_id = b.medicine_id
  WHERE i.invoice_date >= p_from
    AND i.invoice_date <  p_to
  GROUP BY m.medicine_id, m.name
  ORDER BY revenue DESC;
END$$
DELIMITER ;

-- 2) Purchase report (lines with qty, price, line total) for a date window
DROP PROCEDURE IF EXISTS sp_purchase_report;
DELIMITER $$
CREATE PROCEDURE sp_purchase_report(IN p_from DATE, IN p_to DATE)
BEGIN
  SELECT
    b.purchase_date                         AS `date`,
    s.legal_name                            AS supplier,
    m.name                                  AS medicine,
    b.batch_code                             AS batch,
    b.expiry_date                            AS expiry,
    COALESCE(lin.qty_in,0)                  AS qty,
    b.purchase_price                         AS price,
    COALESCE(lin.qty_in,0) * b.purchase_price AS line_total
  FROM med_batch b
  JOIN supplier s ON s.supplier_id = b.supplier_id
  JOIN medicine m ON m.medicine_id = b.medicine_id
  LEFT JOIN (
    SELECT batch_id, SUM(qty_delta) AS qty_in
      FROM inventory_ledger
     WHERE ref_type='PURCHASE'
     GROUP BY batch_id
  ) lin ON lin.batch_id = b.batch_id
  WHERE b.purchase_date >= p_from
    AND b.purchase_date < DATE_ADD(p_to, INTERVAL 1 DAY)
  ORDER BY b.purchase_date DESC, s.legal_name, m.name;
END$$
DELIMITER ;

-- 3) Customer revenue (per day, units & revenue) for a date window
DROP PROCEDURE IF EXISTS sp_customer_revenue;
DELIMITER $$
CREATE PROCEDURE sp_customer_revenue(IN p_from DATE, IN p_to DATE)
BEGIN
  SELECT
    COALESCE(c.full_name,'Walk-in Customer') AS customer,
    DATE(i.invoice_date)                     AS day,
    SUM(ii.qty)                              AS units,
    SUM(ii.qty * ii.unit_price)              AS revenue
  FROM invoice i
  JOIN invoice_item ii ON ii.invoice_id = i.invoice_id
  LEFT JOIN customer c ON c.customer_id = i.customer_id
  WHERE i.invoice_date >= p_from
    AND i.invoice_date < DATE_ADD(p_to, INTERVAL 1 DAY)
  GROUP BY customer, day
  ORDER BY revenue DESC, customer, day;
END$$
DELIMITER ;
