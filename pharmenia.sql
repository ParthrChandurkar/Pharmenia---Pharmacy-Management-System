-- =========================================================
-- PHARMENIA — Full Database (MySQL 8 / 5.7 compatible)
-- Includes: CRUD & Search, 3NF schema, triggers, cursor,
--           stored function & procedures, views, sample data
-- =========================================================

-- ---------- SAFETY: start clean ----------
DROP DATABASE IF EXISTS pharmenia;
CREATE DATABASE pharmenia
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;
USE pharmenia;

-- =========================================================
-- 1) TABLES (3NF, clearly separated master/header/line/ledger)
-- =========================================================

-- 1.1  Customers (1 row kept for Walk-in via unique)
CREATE TABLE customer (
  customer_id   BIGINT PRIMARY KEY AUTO_INCREMENT,
  full_name     VARCHAR(120) NOT NULL,
  phone         VARCHAR(20),
  email         VARCHAR(160),
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_customer_full_name(full_name)  -- prevents duplicate "Walk-in Customer"
);

-- 1.2  Suppliers (master)
CREATE TABLE supplier (
  supplier_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  legal_name  VARCHAR(160) NOT NULL,
  gstin       VARCHAR(20),
  phone       VARCHAR(20),
  email       VARCHAR(160),
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 1.3  Medicines (master) — 3NF: no repeating groups; form as ENUM
CREATE TABLE medicine (
  medicine_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name        VARCHAR(160) NOT NULL,
  salt        VARCHAR(160),
  form_factor ENUM('TABLET','CAPSULE','SYRUP','INJECTION','OINTMENT','DROPS','OTHER') NOT NULL DEFAULT 'TABLET',
  hsn         VARCHAR(16),                 -- GST HSN code
  mrp         DECIMAL(10,2) NOT NULL,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Search indexes for fast LIKE queries (used by UI)
CREATE INDEX idx_medicine_name  ON medicine(name);
CREATE INDEX idx_medicine_salt  ON medicine(salt);

-- 1.4  Purchase header (optional but good practice)
CREATE TABLE purchase (
  purchase_id     BIGINT PRIMARY KEY AUTO_INCREMENT,
  supplier_id     BIGINT NOT NULL,
  supplier_inv_no VARCHAR(64),
  purchase_date   DATE NOT NULL,
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_purchase_supplier FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id)
);

-- 1.5  Medicine batch (one row per supplier batch)
CREATE TABLE med_batch (
  batch_id        BIGINT PRIMARY KEY AUTO_INCREMENT,
  medicine_id     BIGINT NOT NULL,
  supplier_id     BIGINT NOT NULL,
  supplier_inv_no VARCHAR(64),
  batch_code      VARCHAR(64) NOT NULL,
  expiry_date     DATE NOT NULL,
  purchase_date   DATE NOT NULL,
  purchase_price  DECIMAL(10,2) NOT NULL,
  gst_percent     DECIMAL(5,2) NOT NULL DEFAULT 0,
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_mb_med FOREIGN KEY (medicine_id) REFERENCES medicine(medicine_id),
  CONSTRAINT fk_mb_sup FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id),
  UNIQUE KEY uq_batch_unique (medicine_id, batch_code)
);

-- 1.6  Current inventory per batch (canonical stock table)
CREATE TABLE inventory_batch (
  batch_id      BIGINT PRIMARY KEY,
  qty_available INT NOT NULL DEFAULT 0,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_invb_batch FOREIGN KEY (batch_id) REFERENCES med_batch(batch_id)
);

-- 1.7  Inventory ledger (immutable movements: +PURCHASE, -INVOICE, +/-ADJUST)
CREATE TABLE inventory_ledger (
  ledger_id  BIGINT PRIMARY KEY AUTO_INCREMENT,
  batch_id   BIGINT NOT NULL,
  ref_type   ENUM('PURCHASE','INVOICE','ADJUST') NOT NULL,
  ref_id     BIGINT,
  qty_delta  INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_led_batch FOREIGN KEY (batch_id) REFERENCES med_batch(batch_id),
  INDEX idx_led_batch (batch_id),
  INDEX idx_led_reftype_refid (ref_type, ref_id)
);

-- 1.8  Invoice header (sales)
CREATE TABLE invoice (
  invoice_id   BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  customer_id  BIGINT NULL,
  CONSTRAINT fk_invoice_customer FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);

-- 1.9  Invoice line items (batch-level granularity)
CREATE TABLE invoice_item (
  item_id    BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  batch_id   BIGINT NOT NULL,
  qty        INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  CONSTRAINT fk_ii_inv   FOREIGN KEY (invoice_id) REFERENCES invoice(invoice_id),
  CONSTRAINT fk_ii_batch FOREIGN KEY (batch_id)   REFERENCES med_batch(batch_id)
);

-- 1.10  Temp staging (UI to SP handoff for cursor processing)
CREATE TABLE invoice_items_temp(
  row_id      INT PRIMARY KEY AUTO_INCREMENT,
  medicine_id BIGINT NOT NULL,
  qty         INT NOT NULL
);

-- =========================================================
-- 2) BUSINESS RULES (TRIGGERS) — prevent negative inventory
-- =========================================================
DELIMITER $$

CREATE TRIGGER trg_inv_nonneg_ins
BEFORE INSERT ON inventory_batch
FOR EACH ROW
BEGIN
  IF NEW.qty_available < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Inventory cannot be negative (insert).';
  END IF;
END$$

CREATE TRIGGER trg_inv_nonneg_upd
BEFORE UPDATE ON inventory_batch
FOR EACH ROW
BEGIN
  IF NEW.qty_available < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Inventory cannot be negative (update).';
  END IF;
END$$

DELIMITER ;

-- =========================================================
-- 3) STORED FUNCTION — used by UI grids & search
-- =========================================================
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

-- =========================================================
-- 4) STORED PROCEDURES — CRUD flows, cursor, and reports
-- =========================================================

-- 4.1 Add medicine (normalized insert from UI)
DELIMITER $$

CREATE PROCEDURE sp_add_medicine(
  IN p_name VARCHAR(160),
  IN p_salt VARCHAR(160),
  IN p_form VARCHAR(32),
  IN p_hsn  VARCHAR(16),
  IN p_mrp  DECIMAL(10,2)
)
BEGIN
  INSERT INTO medicine(name, salt, form_factor, hsn, mrp)
  VALUES(p_name, NULLIF(p_salt,''), p_form, NULLIF(p_hsn,''), p_mrp);
END$$

DELIMITER ;

-- 4.2 Purchase stock (creates batch + inventory + ledger)
DELIMITER $$

CREATE PROCEDURE sp_purchase_stock(
  IN p_supplier_id    BIGINT,
  IN p_supplier_inv   VARCHAR(64),
  IN p_purchase_date  DATE,
  IN p_medicine_id    BIGINT,
  IN p_batch_code     VARCHAR(64),
  IN p_expiry_date    DATE,
  IN p_purchase_price DECIMAL(10,2),
  IN p_qty            INT,
  IN p_gst_percent    DECIMAL(5,2)
)
BEGIN
  DECLARE v_batch BIGINT;

  -- Optional header (good bookkeeping)
  INSERT INTO purchase(supplier_id, supplier_inv_no, purchase_date)
  VALUES(p_supplier_id, NULLIF(p_supplier_inv,''), p_purchase_date);

  -- Batch record
  INSERT INTO med_batch(
    medicine_id, supplier_id, supplier_inv_no, batch_code,
    expiry_date, purchase_date, purchase_price, gst_percent
  ) VALUES (
    p_medicine_id, p_supplier_id, NULLIF(p_supplier_inv,''), p_batch_code,
    p_expiry_date, p_purchase_date, p_purchase_price, p_gst_percent
  );
  SET v_batch = LAST_INSERT_ID();

  -- Ensure inventory row exists
  INSERT INTO inventory_batch(batch_id, qty_available) VALUES(v_batch, 0)
  ON DUPLICATE KEY UPDATE qty_available = qty_available;

  -- Add stock (+qty)
  UPDATE inventory_batch
     SET qty_available = qty_available + p_qty
   WHERE batch_id = v_batch;

  -- Ledger write
  INSERT INTO inventory_ledger(batch_id, ref_type, ref_id, qty_delta)
  VALUES(v_batch, 'PURCHASE', NULL, p_qty);
END$$

DELIMITER ;

-- 4.3 Create invoice (CURSOR over temp lines; FIFO by earliest expiry)
DELIMITER $$

CREATE PROCEDURE sp_invoice_create(
  IN  p_customer_id BIGINT,
  OUT p_invoice_id  BIGINT
)
BEGIN
  DECLARE v_med_id    BIGINT;
  DECLARE v_needed    INT;
  DECLARE v_batch_id  BIGINT;
  DECLARE v_take      INT;
  DECLARE v_unit_price DECIMAL(10,2);
  DECLARE done INT DEFAULT 0;

  DECLARE cur CURSOR FOR
    SELECT medicine_id, qty
      FROM invoice_items_temp
     ORDER BY row_id;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

  INSERT INTO invoice(customer_id) VALUES(p_customer_id);
  SET p_invoice_id = LAST_INSERT_ID();

  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO v_med_id, v_needed;
    IF done = 1 THEN LEAVE read_loop; END IF;

    WHILE v_needed > 0 DO
      -- Find earliest non-expired batch with stock
      SELECT b.batch_id, m.mrp
        INTO v_batch_id, v_unit_price
        FROM med_batch b
        JOIN medicine m      ON m.medicine_id = b.medicine_id
        JOIN inventory_batch inv ON inv.batch_id = b.batch_id
       WHERE b.medicine_id = v_med_id
         AND b.expiry_date >= CURDATE()
         AND inv.qty_available > 0
       ORDER BY b.expiry_date ASC, b.batch_id ASC
       LIMIT 1;

      IF v_batch_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Insufficient stock to fulfill invoice.';
      END IF;

      SET v_take = LEAST(v_needed, (SELECT qty_available FROM inventory_batch WHERE batch_id = v_batch_id));

      INSERT INTO invoice_item(invoice_id, batch_id, qty, unit_price)
      VALUES(p_invoice_id, v_batch_id, v_take, v_unit_price);

      UPDATE inventory_batch
         SET qty_available = qty_available - v_take
       WHERE batch_id = v_batch_id;

      INSERT INTO inventory_ledger(batch_id, ref_type, ref_id, qty_delta)
      VALUES(v_batch_id, 'INVOICE', p_invoice_id, -v_take);

      SET v_needed = v_needed - v_take;
      SET v_batch_id = NULL;
    END WHILE;
  END LOOP;
  CLOSE cur;

  -- Clear staging once done
  TRUNCATE TABLE invoice_items_temp;
END$$

DELIMITER ;

-- 4.4 Sales summary (for Inventory Reports tab)
DELIMITER $$

CREATE PROCEDURE sp_sales_summary(IN p_from DATETIME, IN p_to DATETIME)
BEGIN
  SELECT
    m.medicine_id,
    m.name,
    SUM(ii.qty)              AS units_sold,
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

-- 4.5 Business reports (purchases; customer revenue) for the new tab
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

-- =========================================================
-- 5) VIEWS — report helpers & dashboard
-- =========================================================

-- Per-medicine current stock
CREATE OR REPLACE VIEW vw_medicine_stock AS
SELECT
  b.medicine_id,
  SUM(inv.qty_available) AS qty_available
FROM med_batch b
JOIN inventory_batch inv ON inv.batch_id = b.batch_id
GROUP BY b.medicine_id;

-- Top sellers (last 90 days)
CREATE OR REPLACE VIEW vw_top_sellers AS
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

-- =========================================================
-- 6) SEED DATA — minimal, so UI works immediately
-- =========================================================

-- Keep one Walk-in customer
INSERT INTO customer(full_name) VALUES ('Walk-in Customer')
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name);

-- A sample supplier
INSERT INTO supplier(legal_name, gstin, phone)
VALUES ('Pulse Distributors', '27ABCDE1234F1Z5', '9999999999');

-- One medicine (Paracetamol)
CALL sp_add_medicine('Paracetamol', 'Acetaminophen', 'TABLET', '3004', 20.00);

-- Buy stock: 100 units, expiry in ~10 months
CALL sp_purchase_stock(
  (SELECT supplier_id FROM supplier WHERE legal_name='Pulse Distributors' LIMIT 1),
  'INV-001',
  CURDATE(),
  (SELECT medicine_id FROM medicine WHERE name='Paracetamol' LIMIT 1),
  'PC-01',
  DATE_ADD(CURDATE(), INTERVAL 300 DAY),
  8.00,   -- purchase price
  100,    -- quantity
  12.00   -- GST %
);

-- Quick sanity checks (optional)
SELECT * FROM vw_medicine_stock;
SELECT * FROM vw_top_sellers LIMIT 1;
