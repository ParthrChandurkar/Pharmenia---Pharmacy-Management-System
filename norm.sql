---------------------------
--UNF 
---------------------------
-- Repeating items in one column (bad), and customer details repeated per invoice
CREATE TABLE sales_unf (
  invoice_no     INT,
  invoice_date   DATE,
  customer_name  VARCHAR(120),
  customer_phone VARCHAR(20),
  -- e.g. "Paracetamol|2|20.00; Amoxicillin|1|35.00"
  items          TEXT
);
--------------------------------
--1NF
--------------------------------
-- Each item is its own row; atomic columns only
CREATE TABLE sales_1nf (
  invoice_no     INT,
  invoice_date   DATE,
  customer_name  VARCHAR(120),
  customer_phone VARCHAR(20),
  line_no        INT,               -- item row number
  med_name       VARCHAR(160),
  qty            INT,
  unit_price     DECIMAL(10,2),
  PRIMARY KEY (invoice_no, line_no) -- still one “big” table
);
---------------------------------------
--2NF
---------------------------------------
-- Invoice header: facts that depend only on invoice_no
CREATE TABLE invoice (
  invoice_id    BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_no    INT UNIQUE,         -- keep natural no. if you want
  invoice_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  customer_name  VARCHAR(120),
  customer_phone VARCHAR(20)
);

-- Invoice detail: facts that depend on (invoice_no, line_no)
CREATE TABLE invoice_item_flat (
  invoice_no   INT,
  line_no      INT,
  med_name     VARCHAR(160),
  qty          INT,
  unit_price   DECIMAL(10,2),
  PRIMARY KEY (invoice_no, line_no),
  FOREIGN KEY (invoice_no) REFERENCES invoice(invoice_no)
);
------------------------------
--3NF
------------------------------
-- Master data: each medicine once
CREATE TABLE medicine (
  medicine_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name        VARCHAR(160) NOT NULL,
  -- plus normalized attributes in your real schema: salt, form_factor, hsn, mrp, etc.
  UNIQUE KEY uq_medicine_name (name)
);

-- Final line table: depend only on keys + FKs (no transitive deps)
CREATE TABLE invoice_item (
  item_id     BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_id  BIGINT NOT NULL,
  medicine_id BIGINT NOT NULL,
  qty         INT NOT NULL,
  unit_price  DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (invoice_id)  REFERENCES invoice(invoice_id),
  FOREIGN KEY (medicine_id) REFERENCES medicine(medicine_id)
);
