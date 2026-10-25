-- =====================================================================================
-- GlowAura Beauty | 03_business_queries.sql
-- Views for Power BI + the 5 business questions. Run scripts 01 and 02 first.
-- "Revenue" = line_total of DELIVERED orders only (counted_in_revenue = 1).
-- Profit and margin use only lines whose product cost is known (cost_price is blank for some products).
-- =====================================================================================
USE glowaura;

-- ---------------------------------------------------------------- VIEW 1: one row per order line, everything joined
CREATE OR REPLACE VIEW vw_sales AS
SELECT d.order_detail_id, d.order_id, o.order_date, YEAR(o.order_date) AS order_year, MONTH(o.order_date) AS month_num,
       DATE_FORMAT(o.order_date, '%Y-%m') AS order_month, o.channel, o.order_status,
       (o.order_status = 'Delivered') AS counted_in_revenue, o.payment_method,
       o.customer_id, c.city AS customer_city, c.state AS customer_state, c.gender, c.loyalty_tier, c.acquisition_channel,
       o.store_id, s.store_name, s.store_type, s.city AS store_city,
       o.campaign_id, cp.campaign_name, cp.channel AS campaign_channel,
       d.product_id, p.product_name, p.brand, p.category, p.sub_category,
       d.quantity, d.unit_price, d.discount_pct, d.line_total,
       d.quantity * p.cost_price AS cost_total,
       d.line_total - d.quantity * p.cost_price AS profit
FROM order_details d
JOIN orders_clean o         ON o.order_id    = d.order_id
LEFT JOIN customers c       ON c.customer_id = o.customer_id
LEFT JOIN stores s          ON s.store_id    = o.store_id
LEFT JOIN campaigns cp      ON cp.campaign_id = o.campaign_id
LEFT JOIN products p        ON p.product_id  = d.product_id;

-- ---------------------------------------------------------------- VIEW 2: one row per customer with RFM scores
CREATE OR REPLACE VIEW vw_customer_rfm AS
WITH cust AS (
  SELECT customer_id, COUNT(DISTINCT order_id) AS frequency, ROUND(SUM(line_total), 2) AS monetary,
         MAX(order_date) AS last_order_date
  FROM vw_sales WHERE counted_in_revenue = 1 AND customer_id IS NOT NULL GROUP BY customer_id),
ref AS (SELECT MAX(order_date) AS last_day FROM orders_clean)
SELECT c.*, DATEDIFF(ref.last_day, c.last_order_date) AS recency_days,
       NTILE(5) OVER (ORDER BY DATEDIFF(ref.last_day, c.last_order_date) DESC) AS r_score,   -- 5 = bought most recently
       NTILE(5) OVER (ORDER BY c.frequency, c.monetary) AS f_score,                          -- 5 = buys most often
       NTILE(5) OVER (ORDER BY c.monetary) AS m_score                                        -- 5 = spends most
FROM cust c CROSS JOIN ref;

-- ---------------------------------------------------------------- VIEW 3: one row per campaign
CREATE OR REPLACE VIEW vw_campaign_performance AS
SELECT cp.campaign_id, cp.campaign_name, cp.channel, cp.start_date, cp.end_date, cp.budget, cp.target_category,
       COUNT(DISTINCT v.order_id) AS orders, ROUND(SUM(v.line_total), 0) AS revenue,
       ROUND(SUM(v.line_total) / cp.budget, 2) AS roas,
       ROUND(100 * (SUM(v.line_total) - cp.budget) / cp.budget, 0) AS roi_pct
FROM campaigns cp
LEFT JOIN vw_sales v ON v.campaign_id = cp.campaign_id AND v.counted_in_revenue = 1
GROUP BY cp.campaign_id, cp.campaign_name, cp.channel, cp.start_date, cp.end_date, cp.budget, cp.target_category;

-- =====================================================================================
-- QUESTION 1: Which categories earn the most revenue and profit?
-- =====================================================================================
-- 1A. Revenue, profit and margin by category
SELECT category,
       ROUND(SUM(line_total), 0) AS revenue,
       ROUND(SUM(CASE WHEN cost_total IS NOT NULL THEN line_total - cost_total END), 0) AS profit,
       ROUND(100 * SUM(CASE WHEN cost_total IS NOT NULL THEN line_total - cost_total END)
                 / SUM(CASE WHEN cost_total IS NOT NULL THEN line_total END), 1) AS margin_pct
FROM vw_sales
WHERE counted_in_revenue = 1 AND category IS NOT NULL
GROUP BY category
ORDER BY revenue DESC;

-- 1B. Top 3 products in every category (window function RANK)
WITH p AS (SELECT category, product_name, SUM(line_total) AS revenue
           FROM vw_sales WHERE counted_in_revenue = 1 AND product_id IS NOT NULL GROUP BY category, product_name),
     r AS (SELECT p.*, RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rnk FROM p)
SELECT category, rnk, product_name, ROUND(revenue, 0) AS revenue
FROM r WHERE rnk <= 3 ORDER BY category, rnk;

-- =====================================================================================
-- QUESTION 2: Online vs offline, and which cities and stores perform best?
-- =====================================================================================
-- 2A. Revenue by channel and year, with each channel's share of the year
WITH t AS (SELECT order_year, channel, SUM(line_total) AS revenue
           FROM vw_sales WHERE counted_in_revenue = 1 AND order_year IS NOT NULL GROUP BY order_year, channel)
SELECT order_year, channel, ROUND(revenue, 0) AS revenue,
       ROUND(100 * revenue / SUM(revenue) OVER (PARTITION BY order_year), 1) AS share_pct
FROM t ORDER BY order_year, channel;

-- 2B. City ranking (customer city): revenue, orders and average order value
SELECT RANK() OVER (ORDER BY SUM(line_total) DESC) AS city_rank, customer_city,
       ROUND(SUM(line_total), 0) AS revenue, COUNT(DISTINCT order_id) AS orders,
       ROUND(SUM(line_total) / COUNT(DISTINCT order_id), 0) AS avg_order_value
FROM vw_sales WHERE counted_in_revenue = 1 AND customer_city <> 'Unknown'
GROUP BY customer_city ORDER BY city_rank;

-- 2C. Top 10 retail stores (offline only) with revenue per square foot
SELECT RANK() OVER (ORDER BY SUM(v.line_total) DESC) AS store_rank, v.store_name, v.store_type, v.store_city,
       ROUND(SUM(v.line_total), 0) AS revenue,
       ROUND(SUM(v.line_total) / s.store_size_sqft, 0) AS revenue_per_sqft
FROM vw_sales v JOIN stores s ON s.store_id = v.store_id
WHERE v.counted_in_revenue = 1 AND v.channel = 'Offline'
GROUP BY v.store_id, v.store_name, v.store_type, v.store_city, s.store_size_sqft
ORDER BY store_rank LIMIT 10;

-- =====================================================================================
-- QUESTION 3: What is the ROI of each marketing campaign?
-- ROAS = revenue / budget ; ROI % = (revenue - budget) / budget. Only orders linked to the campaign count.
-- =====================================================================================
-- 3A. Every campaign, best ROI first (campaigns with a missing budget are skipped)
SELECT campaign_name, channel, budget, orders, revenue, roas, roi_pct
FROM vw_campaign_performance WHERE budget IS NOT NULL ORDER BY roi_pct DESC;

-- 3B. Channel summary
SELECT channel, COUNT(*) AS campaigns, SUM(budget) AS total_budget, SUM(revenue) AS total_revenue,
       ROUND(SUM(revenue) / SUM(budget), 2) AS roas,
       ROUND(100 * (SUM(revenue) - SUM(budget)) / SUM(budget), 0) AS roi_pct
FROM vw_campaign_performance WHERE budget IS NOT NULL GROUP BY channel ORDER BY roi_pct DESC;

-- =====================================================================================
-- QUESTION 4: How many customers come back, and where do we lose them?
-- =====================================================================================
-- 4A. Repeat rate (customers with 2 or more delivered orders)
WITH cust AS (SELECT customer_id, COUNT(DISTINCT order_id) AS orders
              FROM vw_sales WHERE counted_in_revenue = 1 AND customer_id IS NOT NULL GROUP BY customer_id)
SELECT COUNT(*) AS buyers, SUM(orders >= 2) AS repeat_buyers,
       ROUND(100 * SUM(orders >= 2) / COUNT(*), 1) AS repeat_rate_pct FROM cust;

-- 4B. Average days between two orders of the same customer (window function LAG)
WITH o AS (SELECT DISTINCT customer_id, order_id, order_date FROM vw_sales
           WHERE counted_in_revenue = 1 AND customer_id IS NOT NULL AND order_date IS NOT NULL),
     g AS (SELECT DATEDIFF(order_date, LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id)) AS gap FROM o)
SELECT ROUND(AVG(gap)) AS avg_days_between_orders FROM g WHERE gap IS NOT NULL;

-- 4C. Churn: customers whose last order was more than 180 days before the last order date in the data
SELECT COUNT(*) AS buyers, SUM(recency_days > 180) AS churned,
       ROUND(100 * SUM(recency_days > 180) / COUNT(*), 1) AS churn_pct
FROM vw_customer_rfm;

-- 4D. Revenue and repeat behaviour by loyalty tier
SELECT c.loyalty_tier, COUNT(*) AS buyers, ROUND(AVG(r.frequency), 1) AS avg_orders, ROUND(SUM(r.monetary), 0) AS revenue
FROM vw_customer_rfm r JOIN customers c ON c.customer_id = r.customer_id
GROUP BY c.loyalty_tier ORDER BY revenue DESC;

-- =====================================================================================
-- QUESTION 5: How much do discounts hurt the margin?
-- =====================================================================================
SELECT CASE WHEN discount_pct = 0 THEN '0%' WHEN discount_pct <= 10 THEN '1-10%' WHEN discount_pct <= 20 THEN '11-20%'
            WHEN discount_pct <= 30 THEN '21-30%' ELSE '31%+' END AS discount_band,
       COUNT(*) AS order_lines, SUM(quantity) AS units, ROUND(AVG(quantity), 2) AS avg_units_per_line,
       ROUND(SUM(line_total), 0) AS revenue,
       ROUND(100 * SUM(CASE WHEN cost_total IS NOT NULL THEN line_total - cost_total END)
                 / SUM(CASE WHEN cost_total IS NOT NULL THEN line_total END), 1) AS margin_pct
FROM vw_sales
WHERE counted_in_revenue = 1 AND discount_pct IS NOT NULL
GROUP BY discount_band ORDER BY MIN(discount_pct);

-- =====================================================================================
-- BONUS: monthly revenue with month-on-month growth (LAG)
-- =====================================================================================
WITH m AS (SELECT order_month, SUM(line_total) AS revenue FROM vw_sales
           WHERE counted_in_revenue = 1 AND order_month IS NOT NULL GROUP BY order_month)
SELECT order_month, ROUND(revenue, 0) AS revenue,
       ROUND(100 * (revenue - LAG(revenue) OVER (ORDER BY order_month)) / LAG(revenue) OVER (ORDER BY order_month), 1) AS mom_growth_pct
FROM m ORDER BY order_month;
