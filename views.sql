-- =========================================================
-- VIEWS (3)
-- =========================================================

-- 1) Per-medicine current stock
DROP VIEW IF EXISTS vw_medicine_stock;
CREATE VIEW vw_medicine_stock AS
SELECT
  b.medicine_id,
  SUM(inv.qty_available) AS qty_available
FROM med_batch b
JOIN inventory_batch inv ON inv.batch_id = b.batch_id
GROUP BY b.medicine_id;

-- 2) Top sellers in last 90 days
DROP VIEW IF EXISTS vw_top_sellers;
CREATE VIEW vw_top_sellers AS
SELECT
  m.medicine_id,
  m.name,
  SUM(ii.qty) AS units_sold_90d
FROM invoice i
JOIN invoice_item ii ON ii.invoice_id = i.invoice_id
JOIN med_batch b     ON b.batch_id    = ii.batch_id
JOIN medicine m      ON m.medicine_id = b.medicine_id
WHERE i.invoice_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY m.medicine_id, m.name
ORDER BY units_sold_90d DESC;

-- 3) Near-expiry batches (next 30 days) with current qty
DROP VIEW IF EXISTS vw_near_expiry_30d;
CREATE VIEW vw_near_expiry_30d AS
SELECT
  b.batch_id,
  m.name       AS medicine,
  b.batch_code,
  b.expiry_date,
  COALESCE(inv.qty_available,0) AS qty_available
FROM med_batch b
LEFT JOIN inventory_batch inv ON inv.batch_id = b.batch_id
JOIN medicine m ON m.medicine_id = b.medicine_id
WHERE b.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
ORDER BY b.expiry_date ASC;