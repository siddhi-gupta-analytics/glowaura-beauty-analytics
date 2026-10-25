"""
GlowAura Beauty - data cleaning pipeline (Python / Pandas)

Usage:  python glowaura_cleaning.py <folder_with_raw_csvs> <output_folder>

Reads the 6 raw CSV files, applies the cleaning rules from the project plan and writes:
  customers_clean.csv, products_clean.csv, stores_clean.csv, campaigns_clean.csv,
  orders_clean.csv, order_details_clean.csv, orphan_rows.csv, cleaning_log.csv

Blank-cell rules used everywhere
  * grouping text columns (gender, city, ...)  -> 'Unknown'
  * email / phone / numbers / dates            -> left blank (NULL), never 0 or a made-up value
  * impossible values (age 999, quantity -1)   -> blank (NULL)
  * values that can be recomputed or recovered from another column/table are recomputed
  * IDs with no parent record                  -> ID blanked, row kept (child rows with no parent order are removed)
"""
import os
import re
import sys

import numpy as np
import pandas as pd

RAW = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "clean_output"
os.makedirs(OUT, exist_ok=True)

LOG = []


def log(table, column, issue, fix, n, blank_treatment=""):
    n = int(n)
    if n > 0:
        LOG.append(dict(table=table, column=column, issue=issue, fix_applied=fix, rows_affected=n,
                        blank_treatment=blank_treatment))


def read(name):
    return pd.read_csv(os.path.join(RAW, name), dtype=str, keep_default_na=False, encoding="utf-8-sig")


def norm(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def squeeze(s):
    return s.str.strip().str.replace(r"\s+", " ", regex=True)


def num(s):
    t = s.str.replace(r"(?i)rs\.?|inr|₹|,|pcs|yrs|sq\s*ft|%", "", regex=True).str.strip()
    return pd.to_numeric(t, errors="coerce")


DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%B %d, %Y", "%d.%m.%Y"]


def parse_dates(s):
    s = s.str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    rem = s != ""
    for f in DATE_FORMATS:
        p = pd.to_datetime(s.where(rem), format=f, errors="coerce")
        ok = p.notna()
        out = out.fillna(p)
        rem = rem & ~ok
    return out, int(rem.sum())  # (parsed dates, count of non-blank strings that could not be parsed)


def canon_map(s, mapping):
    """Map messy text to canonical values using punctuation/case-insensitive keys. Unmapped -> NaN."""
    return s.map(lambda v: mapping.get(norm(v)) if str(v).strip() != "" else np.nan)


def fix_text(df, table, col, mapping, issue="Inconsistent text / casing", blank="Unknown"):
    before = df[col].copy()
    new = canon_map(before, mapping)
    unmapped = new.isna() & (before.str.strip() != "")
    if unmapped.sum():
        print(f"WARNING {table}.{col}: {int(unmapped.sum())} unmapped values", before[unmapped].unique()[:10])
    changed = (new.notna()) & (new != before)
    log(table, col, issue, "Standardised spelling/casing to the valid list", changed.sum(),
        f"blank -> {blank}" if blank else "")
    nb = (before.str.strip() == "").sum()
    log(table, col, "Missing values", f"Filled with '{blank}'" if blank else "Left blank", nb, "")
    return new.fillna(blank) if blank else new


# =====================================================================================
# CUSTOMERS
# =====================================================================================
c = read("customers_raw.csv")
n0 = len(c)
c = c.drop_duplicates().reset_index(drop=True)
log("customers", "(all rows)", "Duplicate rows", "Removed exact duplicate rows", n0 - len(c))
assert c.customer_id.is_unique

before = c.customer_name.copy()
c["customer_name"] = squeeze(c.customer_name).str.title()
log("customers", "customer_name", "Inconsistent text / casing", "Trimmed spaces, Title Case", (before != c.customer_name).sum())


def gender_fix(x):
    x = x.strip().lower()
    if x == "":
        return "Unknown"
    return "Female" if x[0] == "f" else "Male" if x[0] == "m" else "Other"


before = c.gender.copy()
c["gender"] = c.gender.map(gender_fix)
log("customers", "gender", "Inconsistent text / casing", "Mapped to Female / Male / Other", ((before != c.gender) & (before.str.strip() != "")).sum(), "")
log("customers", "gender", "Missing values", "Filled with 'Unknown'", (before.str.strip() == "").sum())

a = num(c.age)
log("customers", "age", "Numbers stored as text", "Removed 'yrs' and converted to number", c.age.str.contains("yrs").sum())
log("customers", "age", "Missing values", "Left blank (NULL)", (c.age.str.strip() == "").sum())
bad = a.notna() & ~a.between(18, 65)
log("customers", "age", "Invalid values", "Ages outside 18-65 set to blank (NULL)", bad.sum())
c["age"] = a.where(a.between(18, 65)).astype("Int64")

e = c.email.str.strip().str.lower()
log("customers", "email", "Inconsistent text / casing", "Converted to lowercase", ((c.email.str.strip() != e) & (e != "")).sum())
valid_email = e.str.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}")
log("customers", "email", "Missing values", "Left blank (NULL)", (e == "").sum())
log("customers", "email", "Invalid values", "Emails without @ or domain dot set to blank (NULL)", ((e != "") & ~valid_email).sum())
c["email"] = e.where(valid_email)


def phone_fix(x):
    x = x.strip()
    if x == "":
        return np.nan
    plus91 = x.startswith("+91")
    d = re.sub(r"\D", "", x)
    if plus91 and len(d) == 12:
        d = d[2:]
    return d if (len(d) == 10 and d[0] in "6789") else np.nan


before = c.phone.copy()
c["phone"] = before.map(phone_fix)
log("customers", "phone", "Inconsistent formats", "Removed +91, dashes and spaces -> 10 digits",
    ((before != c.phone.fillna("")) & c.phone.notna()).sum())
log("customers", "phone", "Missing values", "Left blank (NULL)", (before.str.strip() == "").sum())
log("customers", "phone", "Invalid values", "Not 10 digits -> blank (NULL)", ((before.str.strip() != "") & c.phone.isna()).sum())

CITIES = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Surat", "Jaipur",
          "Lucknow", "Chandigarh", "Indore", "Kochi", "Nagpur", "Bhopal", "Patna", "Vadodara"]
CITY_MAP = {norm(x): x for x in CITIES}
CITY_MAP.update({"bombay": "Mumbai", "bangalore": "Bengaluru", "calcutta": "Kolkata", "madras": "Chennai",
                 "newdelhi": "Delhi"})
raw_state = c.state.copy()
c["city"] = fix_text(c, "customers", "city", CITY_MAP)
# city -> state mapping learned from the data itself (rows that have both)
tmp = pd.DataFrame({"city": c.city, "state": raw_state.str.strip()})
tmp = tmp[(tmp.city != "Unknown") & (tmp.state != "")]
CITY_STATE = tmp.groupby("city").state.agg(lambda s: s.value_counts().index[0]).to_dict()
st = c.city.map(CITY_STATE)
filled_from_city = (raw_state.str.strip() == "") & st.notna()
st = st.where(st.notna(), raw_state.str.strip().replace("", np.nan))
log("customers", "state", "Missing values", "Filled from the city -> state mapping", filled_from_city.sum())
log("customers", "state", "Missing values", "City also unknown -> 'Unknown'", st.isna().sum())
c["state"] = st.fillna("Unknown")

d, unparsed = parse_dates(c.signup_date)
iso = c.signup_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}")
log("customers", "signup_date", "Mixed date formats", "Converted to yyyy-mm-dd", ((~iso) & (c.signup_date.str.strip() != "")).sum())
oor = d.notna() & ~d.between("2023-01-01", "2026-12-31")
log("customers", "signup_date", "Invalid values", "Date after 2026-12-31 -> blank (NULL)", oor.sum())
log("customers", "signup_date", "Missing values", "Left blank (NULL)", (c.signup_date.str.strip() == "").sum())
c["signup_date"] = d.where(d.between("2023-01-01", "2026-12-31"))

TIERS = {norm(x): x for x in ["Bronze", "Silver", "Gold", "Platinum"]}
c["loyalty_tier"] = fix_text(c, "customers", "loyalty_tier", TIERS)
ACQ = {norm(k): v for k, v in {
    "organic": "Organic", "instagram": "Instagram", "insta": "Instagram", "ig": "Instagram",
    "google ads": "Google Ads", "adwords": "Google Ads", "referral": "Referral", "influencer": "Influencer",
    "offline walk-in": "Offline Walk-in", "walk in": "Offline Walk-in", "email": "Email", "tv": "TV/OTT",
    "tv/ott": "TV/OTT"}.items()}
c["acquisition_channel"] = fix_text(c, "customers", "acquisition_channel", ACQ)

# =====================================================================================
# PRODUCTS (first part: everything except mrp recovery, which needs Order_Details)
# =====================================================================================
p = read("products_raw.csv")
n0 = len(p)
p = p.drop_duplicates().reset_index(drop=True)
log("products", "(all rows)", "Duplicate rows", "Removed exact duplicate rows", n0 - len(p))

BRANDS = ["GlowAura Pure", "GlowAura", "DermaDew", "Velvet Hue", "Tresses & Co", "Aroma Luxe"]
BRAND_MAP = {norm(b): b for b in BRANDS}
CATS = {"skincare": "Skincare", "makeup": "Makeup", "haircare": "Haircare", "fragrance": "Fragrance",
        "fragrances": "Fragrance", "bathbody": "Bath & Body", "bathandbody": "Bath & Body"}

before = p.product_name.copy()
nm = squeeze(p.product_name)
up = nm.str.isupper()
nm = nm.where(~up, nm.str.title())
for b in sorted(BRANDS, key=len, reverse=True):  # restore brand capitalisation that title() breaks
    nm = nm.str.replace("^" + re.escape(b.title()), b, regex=True)
p["product_name"] = nm
log("products", "product_name", "Inconsistent text / casing", "Trimmed spaces; fixed UPPERCASE names", (before != nm).sum())

before_b = p.brand.copy()
b = canon_map(before_b, BRAND_MAP)
log("products", "brand", "Inconsistent text / casing", "Standardised to the 6 valid brands", ((b.notna()) & (b != before_b)).sum())
from_name = b.isna()
b_from_name = p.product_name.map(lambda s: next((x for x in sorted(BRANDS, key=len, reverse=True) if s.startswith(x)), np.nan))
b = b.fillna(b_from_name)
log("products", "brand", "Missing values", "Recovered from the start of product_name", (from_name & b.notna()).sum())
log("products", "brand", "Missing values", "Not recoverable -> 'Unknown'", b.isna().sum())
p["brand"] = b.fillna("Unknown")

sub_vals = p.sub_category[p.sub_category.str.strip() != ""]
SUBS = {norm(v): v for v in sub_vals if v == v.title() and v == v.strip()}
before_s = p.sub_category.copy()
s_ = canon_map(before_s, SUBS)
log("products", "sub_category", "Inconsistent text / casing", "Trimmed and fixed casing", ((s_.notna()) & (s_ != before_s)).sum())
s_from_name = p.product_name.map(lambda s: next((v for v in sorted(SUBS.values(), key=len, reverse=True) if s.endswith(v)), np.nan))
miss = s_.isna()
s_ = s_.fillna(s_from_name)
log("products", "sub_category", "Missing values", "Recovered from the end of product_name", (miss & s_.notna()).sum())
p["sub_category"] = s_.fillna("Unknown")

before_c = p.category.copy()
cat = canon_map(before_c, CATS)
log("products", "category", "Inconsistent text / casing", "Standardised to the 5 valid categories", ((cat.notna()) & (cat != before_c)).sum())
sub_to_cat = pd.DataFrame({"s": p.sub_category, "c": cat}).dropna()
sub_to_cat = sub_to_cat[sub_to_cat.s != "Unknown"].groupby("s").c.agg(lambda x: x.value_counts().index[0]).to_dict()
miss = cat.isna()
cat = cat.fillna(p.sub_category.map(sub_to_cat))
log("products", "category", "Missing values", "Recovered from sub_category", (miss & cat.notna()).sum())
p["category"] = cat.fillna("Unknown")

# same product listed twice with different product_id -> keep the lowest id
key = p.product_name.map(norm)
keep = p.groupby(key).product_id.transform("min")
dup_ids = dict(zip(p.product_id[p.product_id != keep], keep[p.product_id != keep]))
log("products", "product_id", "Duplicate rows", "Same product under 2 IDs; kept the lower product_id", len(dup_ids))
p = p[p.product_id == keep].reset_index(drop=True)
assert p.product_id.is_unique

d, _ = parse_dates(p.launch_date)
log("products", "launch_date", "Mixed date formats", "Converted to yyyy-mm-dd",
    ((~p.launch_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}")) & (p.launch_date.str.strip() != "")).sum())
log("products", "launch_date", "Missing values", "Left blank (NULL)", (p.launch_date.str.strip() == "").sum())
p["launch_date"] = d
TRUE = {"yes", "y", "1", "true", "active"}
FALSE = {"no", "n", "0", "false", "inactive"}
before = p.is_active.copy()
p["is_active"] = before.str.strip().str.lower().map(lambda x: True if x in TRUE else (False if x in FALSE else np.nan))
log("products", "is_active", "Inconsistent text / casing", "Mapped Yes/Y/1/Active etc. to TRUE and No/N/0/Inactive to FALSE",
    (before != before.str.strip().str.lower().map(lambda x: "True" if x in TRUE else "False")).sum())

mrp_raw = num(p.mrp)
cost_raw = num(p.cost_price)

# =====================================================================================
# ORDER DETAILS (first part: parse + recover prices from product mode)
# =====================================================================================
dtl = read("order_details_raw.csv")
n0 = len(dtl)
dtl = dtl.drop_duplicates().reset_index(drop=True)
log("order_details", "(all rows)", "Duplicate rows", "Removed exact duplicate rows", n0 - len(dtl))
assert dtl.order_detail_id.is_unique
raw_pid = dtl.product_id
dtl["order_id"] = dtl.order_id.str.strip().str.upper()
dtl["product_id"] = dtl.product_id.str.strip().str.upper().replace(dup_ids)
log("order_details", "product_id", "Inconsistent text / casing", "Converted to UPPERCASE / trimmed", (raw_pid != raw_pid.str.strip().str.upper()).sum())
up_raw = num(dtl.unit_price)
good_up = up_raw.where((up_raw > 0) & (up_raw <= 5000))
mode_price = pd.DataFrame({"p": dtl.product_id, "u": good_up}).dropna().groupby("p").u.agg(lambda x: x.value_counts().index[0])

# products: finish mrp / cost
mrp = mrp_raw.where((mrp_raw > 0) & (mrp_raw <= 5000))
log("products", "mrp", "Numbers stored as text", "Removed currency symbols/commas and converted to number", p.mrp.str.contains(r"₹|Rs|INR|,").sum())
log("products", "mrp", "Invalid values / outliers", "mrp <= 0 or above 5,000 treated as missing", (mrp_raw.notna() & mrp.isna()).sum())
need = mrp.isna()
mrp = mrp.fillna(p.product_id.map(mode_price))
log("products", "mrp", "Missing values", "Recovered from the most common unit_price of that product in Order_Details", (need & mrp.notna()).sum())
log("products", "mrp", "Missing values", "Not recoverable -> left blank (NULL)", mrp.isna().sum())
p["mrp"] = mrp.round(0).astype("Int64")
cost = cost_raw.where(cost_raw > 0)
log("products", "cost_price", "Numbers stored as text", "Removed currency symbols and converted to number", p.cost_price.str.contains(r"₹|Rs|INR|,").sum())
bad = cost.notna() & mrp.notna() & (cost > mrp)
log("products", "cost_price", "Invalid values", "cost_price greater than mrp -> blank (NULL)", bad.sum())
log("products", "cost_price", "Missing values", "Left blank (NULL)", (p.cost_price.str.strip() == "").sum())
p["cost_price"] = cost.where(~bad).round(2)
products = p[["product_id", "product_name", "brand", "category", "sub_category", "mrp", "cost_price", "launch_date", "is_active"]]

# =====================================================================================
# STORES
# =====================================================================================
s = read("stores_raw.csv")
n0 = len(s)
s = s.drop_duplicates().reset_index(drop=True)
log("stores", "(all rows)", "Duplicate rows", "Removed exact duplicate rows", n0 - len(s))
assert s.store_id.is_unique
before = s.city.copy()
s["city"] = fix_text(s, "stores", "city", CITY_MAP)
STYPES = {norm(x): x for x in ["Flagship", "High Street", "Mall Kiosk", "Warehouse"]}
s["store_type"] = fix_text(s, "stores", "store_type", STYPES)
sz = num(s.store_size_sqft)
log("stores", "store_size_sqft", "Numbers stored as text", "Removed 'sq ft' and commas", s.store_size_sqft.str.contains("sq").sum())
ok = (sz > 0) & ((s.store_type == "Warehouse") | (sz <= 5000))
log("stores", "store_size_sqft", "Invalid values / outliers", "Negative size, or a non-warehouse above 5,000 sqft -> blank (NULL)", (sz.notna() & ~ok).sum())
log("stores", "store_size_sqft", "Missing values", "Left blank (NULL)", (s.store_size_sqft.str.strip() == "").sum())
s["store_size_sqft"] = sz.where(ok).astype("Int64")
sc = num(s.staff_count)
log("stores", "staff_count", "Invalid values", "0 staff -> blank (NULL)", (sc <= 0).sum())
log("stores", "staff_count", "Missing values", "Left blank (NULL)", (s.staff_count.str.strip() == "").sum())
s["staff_count"] = sc.where(sc > 0).astype("Int64")
d, _ = parse_dates(s.opening_date)
log("stores", "opening_date", "Mixed date formats", "Converted to yyyy-mm-dd",
    ((~s.opening_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}")) & (s.opening_date.str.strip() != "")).sum())
log("stores", "opening_date", "Missing values", "Left blank (NULL)", (s.opening_date.str.strip() == "").sum())
s["opening_date"] = d
stores = s[["store_id", "store_name", "store_type", "city", "state", "region", "opening_date", "store_size_sqft", "staff_count"]]

# =====================================================================================
# MARKETING CAMPAIGNS
# =====================================================================================
m = read("marketing_campaigns_raw.csv")
n0 = len(m)
m = m.drop_duplicates().reset_index(drop=True)
log("campaigns", "(all rows)", "Duplicate rows", "Removed exact duplicate rows", n0 - len(m))
assert m.campaign_id.is_unique
CHN = {norm(x): x for x in ["Instagram", "Google Ads", "Influencer", "Email", "Festive Sale", "In-Store Promo", "TV/OTT"]}
CHN.update({"insta": "Instagram", "ig": "Instagram", "googleads": "Google Ads", "influencers": "Influencer",
            "instorepromo": "In-Store Promo", "tvott": "TV/OTT", "tv": "TV/OTT"})
m["channel"] = fix_text(m, "campaigns", "channel", CHN)


def tidy_name(x):
    x = re.sub(r"\s+", " ", x.strip())
    if x.isupper() or x.islower():
        x = re.sub(r"[A-Za-z]+", lambda g: g.group(0).capitalize(), x)
        x = x.replace("Ott", "OTT").replace("Tv", "TV")
    return x


before = m.campaign_name.copy()
m["campaign_name"] = before.map(tidy_name)
log("campaigns", "campaign_name", "Inconsistent text / casing", "Trimmed spaces and fixed UPPER/lower case", (before != m.campaign_name).sum())
bud_raw = num(m.budget)
log("campaigns", "budget", "Numbers stored as text", "Removed currency symbol/commas and converted to number", m.budget.str.contains("₹").sum())
log("campaigns", "budget", "Missing values", "Left blank (NULL)", (m.budget.str.strip() == "").sum())
med = bud_raw.groupby(m.channel).transform("median")
outl = bud_raw > 20 * med
log("campaigns", "budget", "Outliers", "Budget more than 20x the median of its channel -> blank (NULL)", outl.sum())
m["budget"] = bud_raw.where(~outl).astype("Int64")
sd, _ = parse_dates(m.start_date)
ed, _ = parse_dates(m.end_date)
log("campaigns", "start_date / end_date", "Mixed date formats", "Converted to yyyy-mm-dd",
    ((~m.start_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}")).sum() + (~m.end_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}")).sum()))
bad = ed < sd
log("campaigns", "end_date", "Invalid values", "end_date before start_date -> blank (NULL)", bad.sum())
m["start_date"], m["end_date"] = sd, ed.where(~bad)
base = m.campaign_name.str.replace(r"\s*\d{4}$", "", regex=True)
tc = m.target_category.str.strip()
tcm = {norm(x): x for x in tc[(tc != "") & (tc != tc.str.upper()) & (tc != tc.str.lower())].unique()}  # properly-cased values only
tc2 = canon_map(tc, tcm)
log("campaigns", "target_category", "Inconsistent text / casing", "Fixed casing", ((tc2.notna()) & (tc2 != m.target_category)).sum())
by_base = pd.DataFrame({"b": base, "t": tc2}).dropna().groupby("b").t.agg(lambda x: x.value_counts().index[0]).to_dict()
miss = tc2.isna()
tc2 = tc2.fillna(base.map(by_base))
log("campaigns", "target_category", "Missing values", "Recovered from the same campaign in another year", (miss & tc2.notna()).sum())
log("campaigns", "target_category", "Missing values", "Not recoverable -> 'Unknown'", tc2.isna().sum())
m["target_category"] = tc2.fillna("Unknown")
campaigns = m[["campaign_id", "campaign_name", "channel", "start_date", "end_date", "budget", "target_category", "target_audience"]]

# =====================================================================================
# ORDERS (parents first, then children)
# =====================================================================================
o = read("orders_raw.csv")
n0 = len(o)
o = o.drop_duplicates().reset_index(drop=True)
log("orders", "(all rows)", "Duplicate rows", "Removed exact duplicate rows", n0 - len(o))
assert o.order_id.is_unique
order_ids = set(o.order_id)

# ---- Order Details: remove children without a parent order
dtl_orphan_order = ~dtl.order_id.isin(order_ids)
orphan_rows = dtl[dtl_orphan_order].copy()
log("order_details", "order_id", "Orphan keys (no matching parent)", "Order not found in Orders -> row moved to orphan_rows.csv", dtl_orphan_order.sum())
dtl = dtl[~dtl_orphan_order].reset_index(drop=True)
pid_ok = dtl.product_id.isin(set(products.product_id))
log("order_details", "product_id", "Orphan keys (no matching parent)", "Product not found in Products -> product_id blank, row kept", (~pid_ok).sum(),
    "revenue kept; product attributes unknown")
dtl["product_id"] = dtl.product_id.where(pid_ok)

q_raw = num(dtl.quantity)
log("order_details", "quantity", "Numbers stored as text", "Removed 'pcs' and converted to number", dtl.quantity.str.contains("pcs").sum())
q = q_raw.where(q_raw.between(1, 10))
log("order_details", "quantity", "Invalid values / outliers", "0, negative or above 10 units -> blank (NULL), recovered below if possible", (q_raw.notna() & q.isna()).sum())
log("order_details", "quantity", "Missing values", "Blank, recovered below if possible", (dtl.quantity.str.strip() == "").sum())

mrp_map = products.set_index("product_id").mrp.astype(float)
up_raw = num(dtl.unit_price)
log("order_details", "unit_price", "Numbers stored as text", "Removed currency symbols and converted to number", dtl.unit_price.str.contains(r"₹|Rs|INR|,").sum())
up_valid = up_raw.where((up_raw > 0) & (up_raw <= 5000))
log("order_details", "unit_price", "Invalid values / outliers", "0, negative or above 5,000 -> replaced by product mrp", (up_raw.notna() & up_valid.isna()).sum())
need = up_valid.isna()
up = up_valid.fillna(dtl.product_id.map(mrp_map))
log("order_details", "unit_price", "Missing values", "Filled with the product's mrp (price never changes in this data)", (need & up.notna()).sum())
log("order_details", "unit_price", "Missing values", "No product to look up -> blank (NULL)", up.isna().sum())

dr = dtl.discount_pct.str.strip()
dnum = num(dtl.discount_pct)
frac = dnum.between(0, 1, inclusive="neither")
log("order_details", "discount_pct", "Inconsistent formats", "Removed '%' and turned 0.20 style fractions into 20", (dtl.discount_pct.str.contains("%") | frac).sum())
dnum = dnum.where(~frac, dnum * 100).round(0)
dis = dnum.where(dnum.between(0, 100))
log("order_details", "discount_pct", "Invalid values", "Negative or above 100 -> blank (NULL), recovered below if possible", (dnum.notna() & dis.isna()).sum())
log("order_details", "discount_pct", "Missing values", "Blank, recovered below if possible", (dr == "").sum())

lt_raw = num(dtl.line_total)
log("order_details", "line_total", "Numbers stored as text", "Removed currency symbols/commas and converted to number", dtl.line_total.str.contains(r"₹|Rs|INR|,").sum())

# recover discount from line_total when discount is missing (nearest whole 5%, must reconcile to the paisa)
cand = dis.isna() & q.notna() & up.notna() & lt_raw.notna() & (lt_raw > 0)
d_est = ((1 - lt_raw / (q * up)) * 100)
d_round = (d_est / 5).round() * 5
recon = (q * up * (1 - d_round / 100) - lt_raw).abs() < 0.51
rec_d = cand & recon & d_round.between(0, 60)
dis = dis.where(~rec_d, d_round)
log("order_details", "discount_pct", "Missing values", "Recovered from line_total / (quantity x unit_price)", rec_d.sum())
log("order_details", "discount_pct", "Missing values", "Not recoverable -> blank (NULL)", dis.isna().sum())
# recover quantity from line_total when quantity is missing
cand = q.isna() & up.notna() & dis.notna() & lt_raw.notna() & (lt_raw > 0)
q_est = lt_raw / (up * (1 - dis / 100))
q_round = q_est.round()
rec_q = cand & ((q_est - q_round).abs() < 0.02) & q_round.between(1, 10)
q = q.where(~rec_q, q_round)
log("order_details", "quantity", "Missing values", "Recovered from line_total / (unit_price x (1 - discount))", rec_q.sum())
log("order_details", "quantity", "Missing values", "Not recoverable -> blank (NULL)", q.isna().sum())

lt = (q * up * (1 - dis / 100)).round(2)
mismatch = lt_raw.notna() & lt.notna() & ((lt_raw - lt).abs() > 0.51)
log("order_details", "line_total", "Calculation mismatch", "Recomputed as quantity x unit_price x (1 - discount/100)", mismatch.sum())
log("order_details", "line_total", "Missing values / text", "Recomputed from quantity, unit_price and discount", (lt_raw.isna() & lt.notna()).sum())
log("order_details", "line_total", "Missing values", "Could not recompute (an input is blank) -> blank (NULL)", lt.isna().sum())

dtl["quantity"] = q.astype("Int64")
dtl["unit_price"] = up.round(0).astype("Int64")
dtl["discount_pct"] = dis.astype("Int64")
dtl["line_total"] = lt
order_details = dtl[["order_detail_id", "order_id", "product_id", "quantity", "unit_price", "discount_pct", "line_total"]]

# ---- Orders columns
cust_ids = set(c.customer_id)
raw_cid = o.customer_id.copy()
cid = o.customer_id.str.strip().str.upper()
log("orders", "customer_id", "Inconsistent text / casing", "Converted to UPPERCASE / trimmed", (raw_cid != cid).sum())
log("orders", "customer_id", "Missing values", "Left blank (NULL); order kept", (cid == "").sum(), "order kept for sales, excluded from customer analysis")
orph = (cid != "") & ~cid.isin(cust_ids)
log("orders", "customer_id", "Orphan keys (no matching parent)", "Customer not found in Customers -> customer_id blank, row kept", orph.sum())
o["customer_id"] = cid.where(cid.isin(cust_ids))

store_ids = set(stores.store_id)
sid = o.store_id.str.strip().str.upper()
log("orders", "store_id", "Missing values", "Left blank (NULL); order kept", (sid == "").sum())
orph = (sid != "") & ~sid.isin(store_ids)
log("orders", "store_id", "Orphan keys (no matching parent)", "Store not found in Stores -> store_id blank, row kept", orph.sum())
o["store_id"] = sid.where(sid.isin(store_ids))

d, _ = parse_dates(o.order_date)
log("orders", "order_date", "Mixed date formats", "Converted to yyyy-mm-dd",
    ((~o.order_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}")) & (o.order_date.str.strip() != "")).sum())
oor = d.notna() & ~d.between("2024-01-01", "2026-12-31")
log("orders", "order_date", "Invalid values", "Date outside 2024-01-01 to 2026-12-31 -> blank (NULL)", oor.sum())
o["order_date"] = d.where(d.between("2024-01-01", "2026-12-31"))

CH = {"online": "Online", "ecommerce": "Online", "web": "Online", "offline": "Offline", "instore": "Offline",
      "store": "Offline", "retail": "Offline"}
before = o.channel.copy()
ch = canon_map(before, CH)
log("orders", "channel", "Inconsistent text / casing", "Standardised to Online / Offline", ((ch.notna()) & (ch != before)).sum())
stype = o.store_id.map(stores.set_index("store_id").store_type)
miss = ch.isna()
ch = ch.fillna(stype.map(lambda t: np.nan if pd.isna(t) else ("Online" if t == "Warehouse" else "Offline")))
log("orders", "channel", "Missing values", "Recovered from store_type (Warehouse = Online, other stores = Offline)", (miss & ch.notna()).sum())
log("orders", "channel", "Missing values", "Not recoverable -> 'Unknown'", ch.isna().sum())
o["channel"] = ch.fillna("Unknown")

PAY = {norm(k): v for k, v in {
    "upi": "UPI", "upi payment": "UPI", "credit card": "Credit Card", "cc": "Credit Card", "debit card": "Debit Card",
    "debit": "Debit Card", "dc": "Debit Card", "cod": "COD", "cash on delivery": "COD", "net banking": "Net Banking",
    "netbanking": "Net Banking", "wallet": "Wallet", "e-wallet": "Wallet", "cash": "Cash"}.items()}
o["payment_method"] = fix_text(o, "orders", "payment_method", PAY)

cmp_ids = set(campaigns.campaign_id)
camp = o.campaign_id.str.strip().str.upper()
log("orders", "campaign_id", "Inconsistent text / casing", "Converted to UPPERCASE", ((o.campaign_id != camp) & (camp != "")).sum())
orph = (camp != "") & ~camp.isin(cmp_ids)
log("orders", "campaign_id", "Orphan keys (no matching parent)", "Campaign not found -> blank (blank = 'no campaign')", orph.sum())
o["campaign_id"] = camp.where(camp.isin(cmp_ids))

STA = {"delivered": "Delivered", "cancelled": "Cancelled", "canceled": "Cancelled", "returned": "Returned", "return": "Returned"}
o["order_status"] = fix_text(o, "orders", "order_status", STA)

# order totals / shipping from cleaned details
line_ok = order_details.groupby("order_id").line_total.agg(lambda x: x.notna().all())
line_sum = order_details.groupby("order_id").line_total.sum(min_count=1)
subtotal = o.order_id.map(line_sum)
complete = o.order_id.map(line_ok).fillna(False).astype(bool)

ship_raw = o.shipping_fee.str.strip()
sf = num(ship_raw.where(~ship_raw.str.lower().eq("free"), "0"))
log("orders", "shipping_fee", "Inconsistent formats", "'Free' -> 0 and removed currency symbol", ship_raw.str.lower().eq("free").sum() + ship_raw.str.contains("₹").sum())
need = sf.isna()
rule = np.where((o.channel == "Online") & (subtotal < 499), 49.0, 0.0)
sf = sf.where(~need, pd.Series(rule, index=o.index))
log("orders", "shipping_fee", "Missing values", "Recomputed with the rule: Online and subtotal under 499 -> 49, else 0", need.sum())
o["shipping_fee"] = sf.astype("Int64")

tot_raw = num(o.order_total)
computed = (subtotal + sf).round(2).where(complete)
hi = computed.quantile(0.999) * 1.2
raw_ok = tot_raw.where((tot_raw > 0) & (tot_raw <= hi))
final_total = computed.fillna(raw_ok)
log("orders", "order_total", "Numbers stored as text", "Removed currency symbols/commas and converted to number", o.order_total.str.contains(r"₹|Rs|INR|,").sum())
diff = computed.notna() & tot_raw.notna() & ((computed - tot_raw).abs() > 0.51)
log("orders", "order_total", "Invalid values / outliers", "Negative, zero or wrong totals replaced by SUM(line_total) + shipping_fee", diff.sum())
log("orders", "order_total", "Missing values", "Recomputed as SUM(line_total) + shipping_fee", (tot_raw.isna() & computed.notna()).sum())
fb = computed.isna() & raw_ok.notna()
log("orders", "order_total", "Missing values", "Some line_total blank: kept the raw total when it was plausible", fb.sum())
log("orders", "order_total", "Missing values", "No reliable total -> blank (NULL)", final_total.isna().sum())
o["order_total"] = final_total.round(2)
orders = o[["order_id", "customer_id", "store_id", "order_date", "channel", "payment_method", "campaign_id", "order_status",
            "shipping_fee", "order_total"]]

customers = c[["customer_id", "customer_name", "gender", "age", "email", "phone", "city", "state", "signup_date",
               "loyalty_tier", "acquisition_channel"]]

# =====================================================================================
# CHECKS + WRITE
# =====================================================================================
assert customers.customer_id.is_unique and products.product_id.is_unique and stores.store_id.is_unique
assert campaigns.campaign_id.is_unique and orders.order_id.is_unique and order_details.order_detail_id.is_unique
assert order_details.order_id.isin(orders.order_id).all()
assert orders.customer_id.dropna().isin(customers.customer_id).all()
assert orders.store_id.dropna().isin(stores.store_id).all()
assert orders.campaign_id.dropna().isin(campaigns.campaign_id).all()
assert order_details.product_id.dropna().isin(products.product_id).all()

TABLES = {"customers": customers, "products": products, "stores": stores, "campaigns": campaigns,
          "orders": orders, "order_details": order_details}
for name, df in TABLES.items():
    out = df.copy()
    for col in out.columns:
        if str(out[col].dtype).startswith("datetime"):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    out.to_csv(os.path.join(OUT, f"{name}_clean.csv"), index=False, encoding="utf-8-sig")
orphan_rows.to_csv(os.path.join(OUT, "orphan_rows.csv"), index=False, encoding="utf-8-sig")
pd.DataFrame(LOG).to_csv(os.path.join(OUT, "cleaning_log.csv"), index=False, encoding="utf-8-sig")
for name, df in TABLES.items():
    print(f"{name:14s} {len(df):6d} rows")
print("orphan_rows", len(orphan_rows), "| log entries", len(LOG))
