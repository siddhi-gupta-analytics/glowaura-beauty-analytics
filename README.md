# GlowAura Beauty Analytics

End-to-end data analytics project on a fictional Indian beauty and cosmetics retailer, **GlowAura Beauty**, using Excel, SQL, Python and Power BI.

## Business Problem
GlowAura sells skincare, makeup, haircare, fragrance and bath & body products through online and offline stores across 18 Indian cities. This project cleans raw sales data and finds out what drives revenue, profit and customer loyalty.

## Business Questions
1. Which product categories generate the most revenue and profit?
2. Which channels, cities and stores perform best (online vs offline)?
3. What is the ROI of each marketing campaign?
4. How many customers are repeat buyers, and where does churn happen?
5. How much do discounts reduce profit margin?

## Dataset
Synthetic data (Jan 2024 - Dec 2026, INR) with 6 related tables: Customers, Products, Stores, Marketing Campaigns, Orders and Order Details (about 29,000 raw rows). The raw files contain duplicates, missing values, inconsistent spellings, mixed date formats, numbers stored as text, impossible values, outliers and orphan IDs.

## Workflow
| Stage | Tool | Output |
| --- | --- | --- |
| Data profiling and Customers cleaning | Excel | `data/cleaned/customers_clean.csv` |
| Cleaning of Products, Stores, Campaigns, Order Details | Python (Pandas) | `python/glowaura_cleaning.py` |
| Orders cleaning, keys and business queries | SQL (MySQL) | `sql/*.sql` |
| EDA and RFM customer segmentation | Python | coming soon |
| Pivot dashboard | Excel | `excel/glowaura_clean_data.xlsx` |
| Interactive dashboard | Power BI | coming soon |

## Cleaning approach
- Duplicates removed, spellings and dates standardised, text converted to numbers.
- Blank grouping fields are marked `Unknown`; email, phone, age and dates are left blank (NULL) instead of guessing.
- Impossible values are set to NULL; IDs without a parent record are set to NULL; order totals are recalculated from their lines.
- Every action and its row count is in `reports/cleaning_log.csv`.

## Repository Structure
- `data/raw` - original dirty CSV files and data dictionary
- `data/cleaned` - cleaned datasets
- `excel` - clean workbook and dashboard
- `sql` - import, cleaning and business queries
- `python` - cleaning script, EDA notebooks
- `powerbi` - dashboard files
- `reports` - cleaning log and final report
- `case-studies` - business case studies

## Status
In progress: cleaning and SQL analysis done; dashboards and case studies coming next.

## Author
Siddhi Gupta
