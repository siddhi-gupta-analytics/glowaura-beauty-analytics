-- =====================================================================================
-- GlowAura Beauty | 01_create_and_import.sql
-- Creates the database, loads the CSV files into STAGING tables (everything as text),
-- then copies them into properly typed tables.
--
-- BEFORE YOU RUN:
--   1. Put these 6 files in ONE simple folder, e.g.  C:\glowaura_sql\
--        customers_clean.csv, products_clean.csv, stores_clean.csv,
--        marketing campaigns -> campaigns_clean.csv, order_details_clean.csv, orders_raw.csv
--      (orders_raw.csv is the DIRTY file: you clean it in SQL in script 02)
--   2. Use  Edit > Find and Replace  in Workbench to change  C:/glowaura_sql/  to your folder.
--      Always write the path with forward slashes (/), even on Windows.
--   3. In Workbench: Database > Manage Connections > your connection > Advanced tab >
--      "Others" box: add   OPT_LOCAL_INFILE=1   then reconnect.
--   4. Use the CSV files exactly as downloaded. If you opened a CSV in Excel and saved it again, it now has
--      Windows line endings: use Find and Replace to change  TERMINATED BY '\n'  to  TERMINATED BY '\r\n'
--      in the LOAD DATA lines below (6 places).
-- =====================================================================================

CREATE DATABASE IF NOT EXISTS glowaura CHARACTER SET utf8mb4;
USE glowaura;

SET GLOBAL local_infile = 1;          -- needs an admin (root) login; run once

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS order_details, orders_clean, customers, products, stores, campaigns;
DROP TABLE IF EXISTS stg_customers, stg_products, stg_stores, stg_campaigns, stg_order_details, stg_orders_raw;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------- STAGING TABLES (all text)
CREATE TABLE stg_customers (customer_id VARCHAR(20), customer_name VARCHAR(100), gender VARCHAR(20), age VARCHAR(20),
  email VARCHAR(150), phone VARCHAR(30), city VARCHAR(50), state VARCHAR(50), signup_date VARCHAR(30),
  loyalty_tier VARCHAR(20), acquisition_channel VARCHAR(40));
CREATE TABLE stg_products (product_id VARCHAR(20), product_name VARCHAR(120), brand VARCHAR(40), category VARCHAR(40),
  sub_category VARCHAR(40), mrp VARCHAR(20), cost_price VARCHAR(20), launch_date VARCHAR(30), is_active VARCHAR(20));
CREATE TABLE stg_stores (store_id VARCHAR(20), store_name VARCHAR(100), store_type VARCHAR(30), city VARCHAR(50),
  state VARCHAR(50), region VARCHAR(20), opening_date VARCHAR(30), store_size_sqft VARCHAR(20), staff_count VARCHAR(20));
CREATE TABLE stg_campaigns (campaign_id VARCHAR(20), campaign_name VARCHAR(100), channel VARCHAR(40), start_date VARCHAR(30),
  end_date VARCHAR(30), budget VARCHAR(30), target_category VARCHAR(40), target_audience VARCHAR(40));
CREATE TABLE stg_order_details (order_detail_id VARCHAR(20), order_id VARCHAR(20), product_id VARCHAR(20), quantity VARCHAR(20),
  unit_price VARCHAR(20), discount_pct VARCHAR(20), line_total VARCHAR(30));
CREATE TABLE stg_orders_raw (order_id VARCHAR(20), customer_id VARCHAR(30), store_id VARCHAR(30), order_date VARCHAR(40),
  channel VARCHAR(30), payment_method VARCHAR(40), campaign_id VARCHAR(30), order_status VARCHAR(30),
  shipping_fee VARCHAR(30), order_total VARCHAR(40));

-- ---------------------------------------------------------------- LOAD THE CSV FILES
LOAD DATA LOCAL INFILE 'C:/glowaura_sql/customers_clean.csv' INTO TABLE stg_customers CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\n' IGNORE 1 LINES;
LOAD DATA LOCAL INFILE 'C:/glowaura_sql/products_clean.csv' INTO TABLE stg_products CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\n' IGNORE 1 LINES;
LOAD DATA LOCAL INFILE 'C:/glowaura_sql/stores_clean.csv' INTO TABLE stg_stores CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\n' IGNORE 1 LINES;
LOAD DATA LOCAL INFILE 'C:/glowaura_sql/campaigns_clean.csv' INTO TABLE stg_campaigns CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\n' IGNORE 1 LINES;
LOAD DATA LOCAL INFILE 'C:/glowaura_sql/order_details_clean.csv' INTO TABLE stg_order_details CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\n' IGNORE 1 LINES;
LOAD DATA LOCAL INFILE 'C:/glowaura_sql/orders_raw.csv' INTO TABLE stg_orders_raw CHARACTER SET utf8mb4
  FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\n' IGNORE 1 LINES;

-- Quick check: expected 2000 | 289 | 28 | 29 | 18683 | 8092
SELECT (SELECT COUNT(*) FROM stg_customers) AS customers, (SELECT COUNT(*) FROM stg_products) AS products,
       (SELECT COUNT(*) FROM stg_stores) AS stores, (SELECT COUNT(*) FROM stg_campaigns) AS campaigns,
       (SELECT COUNT(*) FROM stg_order_details) AS order_details, (SELECT COUNT(*) FROM stg_orders_raw) AS orders_raw;

-- ---------------------------------------------------------------- TYPED TABLES (the clean ones)
-- NULLIF(TRIM(x),'') turns empty text into a real NULL; REPLACE(x,'\r','') removes a Windows line-end if present.
CREATE TABLE customers (
  customer_id VARCHAR(10) PRIMARY KEY, customer_name VARCHAR(100), gender VARCHAR(10), age TINYINT UNSIGNED NULL,
  email VARCHAR(150) NULL, phone CHAR(10) NULL, city VARCHAR(40), state VARCHAR(40), signup_date DATE NULL,
  loyalty_tier VARCHAR(10), acquisition_channel VARCHAR(30));
INSERT INTO customers
SELECT customer_id, customer_name, gender, CAST(NULLIF(TRIM(age),'') AS UNSIGNED), NULLIF(TRIM(email),''),
       NULLIF(TRIM(phone),''), city, state, STR_TO_DATE(NULLIF(TRIM(signup_date),''),'%Y-%m-%d'), loyalty_tier,
       TRIM(REPLACE(acquisition_channel,'\r',''))
FROM stg_customers;

CREATE TABLE products (
  product_id VARCHAR(10) PRIMARY KEY, product_name VARCHAR(120), brand VARCHAR(40), category VARCHAR(40),
  sub_category VARCHAR(40), mrp INT NULL, cost_price DECIMAL(10,2) NULL, launch_date DATE NULL, is_active TINYINT(1) NULL);
INSERT INTO products
SELECT product_id, product_name, brand, category, sub_category, CAST(NULLIF(TRIM(mrp),'') AS UNSIGNED),
       CAST(NULLIF(TRIM(cost_price),'') AS DECIMAL(10,2)), STR_TO_DATE(NULLIF(TRIM(launch_date),''),'%Y-%m-%d'),
       CASE TRIM(REPLACE(is_active,'\r','')) WHEN 'True' THEN 1 WHEN 'False' THEN 0 END
FROM stg_products;

CREATE TABLE stores (
  store_id VARCHAR(10) PRIMARY KEY, store_name VARCHAR(100), store_type VARCHAR(20), city VARCHAR(40), state VARCHAR(40),
  region VARCHAR(10), opening_date DATE NULL, store_size_sqft INT NULL, staff_count INT NULL);
INSERT INTO stores
SELECT store_id, store_name, store_type, city, state, region, STR_TO_DATE(NULLIF(TRIM(opening_date),''),'%Y-%m-%d'),
       CAST(NULLIF(TRIM(store_size_sqft),'') AS UNSIGNED), CAST(NULLIF(TRIM(REPLACE(staff_count,'\r','')),'') AS UNSIGNED)
FROM stg_stores;

CREATE TABLE campaigns (
  campaign_id VARCHAR(10) PRIMARY KEY, campaign_name VARCHAR(100), channel VARCHAR(30), start_date DATE NULL,
  end_date DATE NULL, budget INT NULL, target_category VARCHAR(30), target_audience VARCHAR(40));
INSERT INTO campaigns
SELECT campaign_id, campaign_name, channel, STR_TO_DATE(NULLIF(TRIM(start_date),''),'%Y-%m-%d'),
       STR_TO_DATE(NULLIF(TRIM(end_date),''),'%Y-%m-%d'), CAST(NULLIF(TRIM(budget),'') AS UNSIGNED),
       target_category, TRIM(REPLACE(target_audience,'\r',''))
FROM stg_campaigns;

-- order_details is already clean (Python). Its foreign keys are added at the end of script 02,
-- after orders_clean exists.
CREATE TABLE order_details (
  order_detail_id VARCHAR(12) PRIMARY KEY, order_id VARCHAR(12) NOT NULL, product_id VARCHAR(10) NULL,
  quantity TINYINT UNSIGNED NULL, unit_price INT NULL, discount_pct TINYINT UNSIGNED NULL, line_total DECIMAL(12,2) NULL,
  KEY idx_od_order (order_id), KEY idx_od_product (product_id));
INSERT INTO order_details
SELECT order_detail_id, order_id, NULLIF(TRIM(product_id),''), CAST(NULLIF(TRIM(quantity),'') AS UNSIGNED),
       CAST(NULLIF(TRIM(unit_price),'') AS UNSIGNED), CAST(NULLIF(TRIM(discount_pct),'') AS UNSIGNED),
       CAST(NULLIF(TRIM(REPLACE(line_total,'\r','')),'') AS DECIMAL(12,2))
FROM stg_order_details;

-- Final check: expected 2000 | 289 | 28 | 29 | 18683
SELECT (SELECT COUNT(*) FROM customers) AS customers, (SELECT COUNT(*) FROM products) AS products,
       (SELECT COUNT(*) FROM stores) AS stores, (SELECT COUNT(*) FROM campaigns) AS campaigns,
       (SELECT COUNT(*) FROM order_details) AS order_details;
