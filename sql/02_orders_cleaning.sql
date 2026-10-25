-- =====================================================================================
-- GlowAura Beauty | 02_orders_cleaning.sql
-- Cleans the dirty orders table (stg_orders_raw) step by step. Each step makes a new table,
-- so you can look at the result of every step (SELECT * FROM orders_s1 LIMIT 20; ...).
-- Run script 01 first. Expected row counts are written next to each step.
--
-- Rules (same as the project plan):
--   * grouping text -> 'Unknown' when blank        * IDs with no parent -> NULL, order kept
--   * impossible dates -> NULL                     * order_total = SUM(line_total) + shipping_fee
-- =====================================================================================
USE glowaura;
DROP TABLE IF EXISTS orders_s1, orders_s2, orders_s3, orders_s4, orders_clean;

-- ---------------------------------------------------------------- STEP 0: look at the mess
SELECT COUNT(*) AS raw_rows, COUNT(DISTINCT order_id) AS distinct_order_ids FROM stg_orders_raw;   -- 8092 | 7952
SELECT channel, COUNT(*) AS n FROM stg_orders_raw GROUP BY channel ORDER BY n DESC;                -- many spellings
SELECT payment_method, COUNT(*) AS n FROM stg_orders_raw GROUP BY payment_method ORDER BY n DESC;
SELECT order_status, COUNT(*) AS n FROM stg_orders_raw GROUP BY order_status ORDER BY n DESC;

-- ---------------------------------------------------------------- STEP 1: remove duplicate rows
-- ROW_NUMBER() numbers identical rows 1,2,3...; we keep only number 1.
CREATE TABLE orders_s1 AS
SELECT order_id, customer_id, store_id, order_date, channel, payment_method, campaign_id, order_status,
       shipping_fee, order_total
FROM (SELECT r.*, ROW_NUMBER() OVER (PARTITION BY order_id, customer_id, store_id, order_date, channel,
                                                   payment_method, campaign_id, order_status, shipping_fee, order_total
                                      ORDER BY order_id) AS rn
      FROM stg_orders_raw r) x
WHERE rn = 1;
SELECT COUNT(*) AS rows_after_step1, COUNT(DISTINCT order_id) AS unique_ids FROM orders_s1;       -- 7952 | 7952

-- ---------------------------------------------------------------- STEP 2: standardise text and IDs
CREATE TABLE orders_s2 AS
SELECT order_id,
       NULLIF(UPPER(TRIM(customer_id)),'') AS customer_id,
       NULLIF(UPPER(TRIM(store_id)),'')    AS store_id,
       TRIM(order_date)                    AS order_date_txt,
       CASE WHEN LOWER(TRIM(channel)) IN ('online','e-commerce','web') THEN 'Online'
            WHEN LOWER(TRIM(channel)) IN ('offline','in-store','store','retail') THEN 'Offline' END AS channel,   -- blank stays NULL for now
       CASE WHEN LOWER(TRIM(payment_method)) IN ('upi','upi payment') THEN 'UPI'
            WHEN LOWER(TRIM(payment_method)) IN ('credit card','cc') THEN 'Credit Card'
            WHEN LOWER(TRIM(payment_method)) IN ('debit card','debit','dc') THEN 'Debit Card'
            WHEN LOWER(TRIM(payment_method)) IN ('cod','cash on delivery','c.o.d') THEN 'COD'
            WHEN LOWER(TRIM(payment_method)) IN ('net banking','netbanking') THEN 'Net Banking'
            WHEN LOWER(TRIM(payment_method)) IN ('wallet','e-wallet') THEN 'Wallet'
            WHEN LOWER(TRIM(payment_method)) = 'cash' THEN 'Cash'
            ELSE 'Unknown' END AS payment_method,
       NULLIF(UPPER(TRIM(campaign_id)),'') AS campaign_id,      -- blank = order had no campaign (valid)
       CASE WHEN LOWER(TRIM(order_status)) = 'delivered' THEN 'Delivered'
            WHEN LOWER(TRIM(order_status)) IN ('cancelled','canceled') THEN 'Cancelled'
            WHEN LOWER(TRIM(order_status)) IN ('returned','return') THEN 'Returned'
            ELSE 'Unknown' END AS order_status,
       TRIM(shipping_fee) AS shipping_fee_txt,
       TRIM(REPLACE(order_total,'\r','')) AS order_total_txt
FROM orders_s1;
SELECT channel, COUNT(*) AS n FROM orders_s2 GROUP BY channel;            -- Online, Offline, NULL (blank)
SELECT order_status, COUNT(*) AS n FROM orders_s2 GROUP BY order_status;  -- Delivered 7350, Returned 334, Cancelled 188, Unknown 80

-- ---------------------------------------------------------------- STEP 3: dates and numbers
-- Dates come in 5 formats; we test the pattern first (REGEXP) and then convert (STR_TO_DATE).
-- Numbers: remove "Rs." / "INR" first, then keep only digits, dot and minus (this also removes the rupee sign and commas).
CREATE TABLE orders_s3 AS
SELECT order_id, customer_id, store_id,
       CASE WHEN d BETWEEN '2024-01-01' AND '2026-12-31' THEN d END AS order_date,   -- impossible dates -> NULL
       channel, payment_method, campaign_id, order_status,
       CASE WHEN LOWER(shipping_fee_txt) = 'free' THEN 0
            ELSE CAST(NULLIF(REGEXP_REPLACE(REGEXP_REPLACE(shipping_fee_txt,'(?i)rs[.]|inr',''),'[^0-9.-]',''),'') AS DECIMAL(10,2))
       END AS shipping_fee,
       CAST(NULLIF(REGEXP_REPLACE(REGEXP_REPLACE(order_total_txt,'(?i)rs[.]|inr',''),'[^0-9.-]',''),'') AS DECIMAL(12,2)) AS total_raw
FROM (SELECT s.*,
             CASE WHEN order_date_txt REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'        THEN STR_TO_DATE(order_date_txt,'%Y-%m-%d')
                  WHEN order_date_txt REGEXP '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'        THEN STR_TO_DATE(order_date_txt,'%d/%m/%Y')
                  WHEN order_date_txt REGEXP '^[0-9]{2}-[A-Za-z]{3}-[0-9]{4}$'     THEN STR_TO_DATE(order_date_txt,'%d-%b-%Y')
                  WHEN order_date_txt REGEXP '^[A-Za-z]+ [0-9]{1,2}, [0-9]{4}$'    THEN STR_TO_DATE(order_date_txt,'%M %d, %Y')
                  WHEN order_date_txt REGEXP '^[0-9]{2}[.][0-9]{2}[.][0-9]{4}$'    THEN STR_TO_DATE(order_date_txt,'%d.%m.%Y')
             END AS d
      FROM orders_s2 s) t;
SELECT MIN(order_date) AS first_date, MAX(order_date) AS last_date, SUM(order_date IS NULL) AS null_dates FROM orders_s3;   -- 2024-01-01 | 2026-12-31 | 20

-- ---------------------------------------------------------------- STEP 4: check parent IDs and recover channel
-- LEFT JOIN to the parent tables: if the parent is missing the ID is set to NULL (the order itself is kept).
CREATE TABLE orders_s4 AS
SELECT s.order_id,
       CASE WHEN c.customer_id IS NOT NULL THEN s.customer_id END AS customer_id,
       CASE WHEN st.store_id   IS NOT NULL THEN s.store_id    END AS store_id,
       s.order_date,
       COALESCE(s.channel,                                   -- blank channel: Warehouse = Online, any other store = Offline
                CASE WHEN st.store_type = 'Warehouse' THEN 'Online' WHEN st.store_type IS NOT NULL THEN 'Offline' END,
                'Unknown') AS channel,
       s.payment_method,
       CASE WHEN cp.campaign_id IS NOT NULL THEN s.campaign_id END AS campaign_id,
       s.order_status, s.shipping_fee, s.total_raw
FROM orders_s3 s
LEFT JOIN customers c  ON c.customer_id  = s.customer_id
LEFT JOIN stores    st ON st.store_id    = s.store_id
LEFT JOIN campaigns cp ON cp.campaign_id = s.campaign_id;
SELECT SUM(customer_id IS NULL) AS no_customer, SUM(store_id IS NULL) AS no_store, SUM(channel='Unknown') AS unknown_channel
FROM orders_s4;                                                                      -- 105 | 174 | 3

-- ---------------------------------------------------------------- STEP 5: shipping fee and order total
-- order_total = SUM(line_total of its lines) + shipping_fee. This fixes negative, zero, text and outlier totals together.
-- If some line_total is blank we cannot add up, so we keep the raw total only if it looks sensible (0 to 10,000).
CREATE TABLE orders_clean (
  order_id VARCHAR(12) PRIMARY KEY, customer_id VARCHAR(10) NULL, store_id VARCHAR(10) NULL, order_date DATE NULL,
  channel VARCHAR(10), payment_method VARCHAR(15), campaign_id VARCHAR(10) NULL, order_status VARCHAR(10),
  shipping_fee INT, order_total DECIMAL(12,2) NULL);
INSERT INTO orders_clean
SELECT order_id, customer_id, store_id, order_date, channel, payment_method, campaign_id, order_status, fee,
       CASE WHEN n_lines > 0 AND null_lines = 0 THEN ROUND(subtotal + fee, 2)
            WHEN total_raw > 0 AND total_raw <= 10000 THEN total_raw END AS order_total
FROM (SELECT s.*, l.subtotal, l.n_lines, l.null_lines,
             COALESCE(s.shipping_fee, CASE WHEN s.channel = 'Online' AND l.subtotal < 499 THEN 49 ELSE 0 END) AS fee
      FROM orders_s4 s
      LEFT JOIN (SELECT order_id, SUM(line_total) AS subtotal, COUNT(*) AS n_lines, SUM(line_total IS NULL) AS null_lines
                 FROM order_details GROUP BY order_id) l ON l.order_id = s.order_id) z;

-- ---------------------------------------------------------------- STEP 6: keys (links between tables)
ALTER TABLE orders_clean
  ADD CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  ADD CONSTRAINT fk_orders_store    FOREIGN KEY (store_id)    REFERENCES stores(store_id),
  ADD CONSTRAINT fk_orders_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id);
ALTER TABLE order_details
  ADD CONSTRAINT fk_od_order   FOREIGN KEY (order_id)   REFERENCES orders_clean(order_id),
  ADD CONSTRAINT fk_od_product FOREIGN KEY (product_id) REFERENCES products(product_id);
-- If a FOREIGN KEY line gives an error, some ID still has no parent. Find it with, for example:
--   SELECT * FROM orders_clean o LEFT JOIN customers c ON c.customer_id = o.customer_id
--   WHERE o.customer_id IS NOT NULL AND c.customer_id IS NULL;

-- ---------------------------------------------------------------- STEP 7: final checks (compare with the numbers on the right)
SELECT COUNT(*)                            AS orders,            -- 7952
       SUM(order_status = 'Delivered')     AS delivered,         -- 7350
       SUM(customer_id IS NULL)            AS no_customer,       -- 105
       SUM(store_id IS NULL)               AS no_store,          -- 174
       SUM(campaign_id IS NULL)            AS no_campaign,       -- 6345
       SUM(order_date IS NULL)             AS no_date,           -- 20
       SUM(order_total IS NULL)            AS no_total,          -- 0
       ROUND(SUM(order_total), 2)          AS total_value        -- 13836209.00
FROM orders_clean;

DROP TABLE orders_s1, orders_s2, orders_s3, orders_s4;      -- tidy up the step tables when you are happy
