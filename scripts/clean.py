"""Clean WFP food price data for Nigeria and Niger into Power BI-ready tables.

Inputs  (data/raw/):   wfp_food_prices_nga.csv, wfp_food_prices_ner.csv  (HDX, WFP)
Outputs (data/clean/):
  prices.csv          one row per market x commodity x unit x price type x month,
                      with price per standard unit (kg / litre / piece) in local currency and USD
  markets.csv         market list with state, LGA, zone, coordinates and coverage dates
  commodities.csv     commodity list with harmonised group used for the Nigeria vs Niger page
  fx_monthly.csv      implied local-currency-per-USD rate by country and month (median of price/usdprice)
  coverage.csv        rows and markets by country, zone, state and year
  dates.csv           month calendar (1990-2026) for the Power BI date table
  countries.csv       country list with currency

Usage:  python scripts/clean.py
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "clean"

ZONES = {  # Nigeria's six geopolitical zones (all 36 states + FCT)
    "North Central": ["Benue", "Kogi", "Kwara", "Nasarawa", "Niger", "Plateau", "Federal Capital Territory", "FCT"],
    "North East": ["Adamawa", "Bauchi", "Borno", "Gombe", "Taraba", "Yobe"],
    "North West": ["Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Sokoto", "Zamfara"],
    "South East": ["Abia", "Anambra", "Ebonyi", "Enugu", "Imo"],
    "South South": ["Akwa Ibom", "Bayelsa", "Cross River", "Delta", "Edo", "Rivers"],
    "South West": ["Ekiti", "Lagos", "Ogun", "Ondo", "Osun", "Oyo"],
}
STATE_TO_ZONE = {s: z for z, states in ZONES.items() for s in states}

# Harmonised groups so the same food can be compared across the two countries.
GROUPS = {
    "Millet": "Millet",
    "Sorghum": "Sorghum", "Sorghum (white)": "Sorghum", "Sorghum (brown)": "Sorghum", "Sorghum (local)": "Sorghum",
    "Maize": "Maize", "Maize (white)": "Maize", "Maize (yellow)": "Maize",
    "Rice (imported)": "Rice (imported)",
    "Rice (local)": "Rice (local)", "Rice (milled, local)": "Rice (local)",
    "Cowpeas": "Cowpeas", "Cowpeas (white)": "Cowpeas", "Cowpeas (brown)": "Cowpeas", "Beans (niebe)": "Cowpeas",
    "Beans (white)": "Beans", "Beans (red)": "Beans",
    "Gari (white)": "Gari", "Cassava meal (gari, yellow)": "Gari",
    "Yam": "Yam", "Yam (Abuja)": "Yam",
    "Oil (palm)": "Palm oil", "Oil (vegetable)": "Vegetable oil",
}

UNIT_RE = re.compile(r"^\s*(?P<qty>[\d.]+)?\s*(?P<u>KG|G|L|pcs|Unit|Tubers)\s*$", re.I)


def parse_unit(unit: str):
    """'2.7 KG' -> (2.7, 'kg'); '400 G' -> (0.4, 'kg'); '100 L' -> (100, 'litre'); '30 pcs' -> (30, 'piece')."""
    m = UNIT_RE.match(str(unit))
    if not m:
        return np.nan, None
    qty = float(m.group("qty")) if m.group("qty") else 1.0
    u = m.group("u").lower()
    if u == "g":
        return qty / 1000, "kg"
    if u == "kg":
        return qty, "kg"
    if u == "l":
        return qty, "litre"
    return qty, "piece"  # pcs, Unit, Tubers


def load(path: Path, country: str) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["date"])
    if str(d.iloc[0]["date"]).startswith("#"):  # HXL tag row, present in some HDX downloads
        d = d.iloc[1:]
    d["country"] = country
    return d


def main():
    CLEAN.mkdir(parents=True, exist_ok=True)
    d = pd.concat([load(RAW / "wfp_food_prices_nga.csv", "Nigeria"),
                   load(RAW / "wfp_food_prices_ner.csv", "Niger")], ignore_index=True)
    n_raw = len(d)

    d = d.rename(columns={"admin1": "state", "admin2": "lga", "price": "price_local", "usdprice": "price_usd"})
    d["zone"] = np.where(d.country == "Nigeria", d.state.map(STATE_TO_ZONE), "Niger")
    if d.loc[d.country == "Nigeria", "zone"].isna().any():
        raise ValueError(f"State(s) without a zone: {d.loc[(d.country=='Nigeria') & d.zone.isna(), 'state'].unique()}")

    parsed = d["unit"].map(parse_unit)
    d["unit_qty"] = [p[0] for p in parsed]
    d["std_unit"] = [p[1] for p in parsed]
    bad_units = d[d.std_unit.isna()].unit.unique()
    if len(bad_units):
        raise ValueError(f"Unparsed units: {bad_units}")
    d["price_per_unit_local"] = d.price_local / d.unit_qty
    d["price_per_unit_usd"] = d.price_usd / d.unit_qty

    d["commodity_group"] = d.commodity.map(GROUPS).fillna(d.commodity)
    # A few foods are priced both by weight and by count (e.g. yam per kg and per 100 tubers).
    # Mark the most common standard unit per commodity so averages never mix kg and pieces.
    main_unit = d.groupby("commodity").std_unit.agg(lambda s: s.value_counts().idxmax())
    d["is_main_unit"] = d.std_unit == d.commodity.map(main_unit)
    d["is_aggregate"] = d.priceflag.str.contains("aggregate")
    d["month"] = d.date.dt.to_period("M").dt.to_timestamp()

    # Outlier flag: more than 5x above or below the median for the same country, commodity,
    # standard unit, price type and month. Flagged, not removed.
    key = ["country", "commodity", "std_unit", "pricetype", "month"]
    med = d.groupby(key).price_per_unit_local.transform("median")
    ratio = d.price_per_unit_local / med
    outlier = (ratio > 5) | (ratio < 0.2)

    # Unit break: a whole series (same zone, food, unit and price type) jumps more than 3x, or falls
    # below a third, against the months around it, e.g. sugar "500 G" prices rising 5x in one month
    # because the pack size changed in the source. A month is flagged when it breaks from both the
    # previous and the following six months (one side only at the start or end of a series), or when
    # a break lasts until the end of the series (at most six months). Gaps over 12 months are not bridged.
    series = ["country", "zone", "commodity", "std_unit", "pricetype"]
    monthly = (d[~outlier].groupby(series + ["month"]).price_per_unit_local.median()
                 .rename("med").reset_index().sort_values(series + ["month"]))

    def off(value, ref):
        return ref is not None and (value > 3 * ref or value < ref / 3)

    broken = []
    for key, g in monthly.groupby(series, sort=False):
        months, meds = list(g.month), list(g.med)
        n = len(meds)

        def window(i, step):
            idx = range(i - 1, max(-1, i - 7), -1) if step < 0 else range(i + 1, min(n, i + 7))
            vals = [meds[j] for j in idx if abs((months[i] - months[j]).days) <= 366]
            return float(np.median(vals)) if vals else None

        flagged = set()
        for i in range(n):
            prev, nxt = window(i, -1), window(i, +1)
            if prev is not None and nxt is not None:
                bad = off(meds[i], prev) and off(meds[i], nxt)
            else:
                bad = off(meds[i], prev if prev is not None else nxt)
            if bad:
                flagged.add(i)
        for k in range(max(1, n - 6), n):  # break that persists to the end of the series
            prev = window(k, -1)
            if prev is not None and all(off(meds[j], prev) for j in range(k, n)):
                flagged.update(range(k, n))
                break
        broken += [tuple(key) + (months[i],) for i in sorted(flagged)]
    broken_idx = pd.MultiIndex.from_tuples(broken, names=series + ["month"])
    unit_break = d.set_index(series + ["month"]).index.isin(broken_idx)

    # Incomplete month: the latest month(s) for a country where fewer than half the usual markets
    # have reported yet (e.g. Nigeria Sep 2026: 4 markets against about 20).
    per_month = d.groupby(["country", "month"]).market_id.nunique().rename("n").reset_index()
    partial = set()
    for c, g in per_month.groupby("country"):
        g = g.sort_values("month")
        typical = g.n.iloc[-7:-1].median()
        for row in g.iloc[::-1].itertuples(index=False):
            if row.n < typical / 2:
                partial.add((c, row.month))
            else:
                break
    incomplete = pd.Series(list(zip(d.country, d.month)), index=d.index).isin(partial).to_numpy()

    d["exclude_reason"] = np.select([outlier, unit_break, incomplete],
                                    ["outlier", "unit break", "incomplete month"], default="")
    d["exclude"] = d.exclude_reason != ""

    cols = ["month", "country", "zone", "state", "lga", "market", "market_id", "category", "commodity",
            "commodity_group", "pricetype", "unit", "unit_qty", "std_unit", "currency", "price_local",
            "price_usd", "price_per_unit_local", "price_per_unit_usd", "is_main_unit", "is_aggregate", "exclude", "exclude_reason"]
    prices = d[cols].sort_values(["country", "market", "commodity", "month"])
    prices.to_csv(CLEAN / "prices.csv", index=False, float_format="%.4f")

    markets = (d.groupby(["country", "market_id"])
                 .agg(market=("market", "first"), zone=("zone", "first"), state=("state", "first"),
                      lga=("lga", "first"), latitude=("latitude", "first"), longitude=("longitude", "first"),
                      first_month=("month", "min"), last_month=("month", "max"), records=("price_local", "size"))
                 .reset_index())
    markets.to_csv(CLEAN / "markets.csv", index=False)

    commodities = (d.groupby(["commodity"]).agg(category=("category", "first"), commodity_group=("commodity_group", "first"),
                                                 main_unit=("std_unit", lambda s: s.value_counts().idxmax()),
                                                 countries=("country", lambda s: ", ".join(sorted(s.unique()))))
                     .reset_index())
    commodities.to_csv(CLEAN / "commodities.csv", index=False)

    fx = (d[d.price_usd > 0].assign(rate=lambda x: x.price_local / x.price_usd)
            .groupby(["country", "currency", "month"]).rate.median().rename("local_per_usd").reset_index())
    fx.to_csv(CLEAN / "fx_monthly.csv", index=False, float_format="%.2f")

    coverage = (d.groupby(["country", "zone", "state", d.date.dt.year.rename("year")])
                  .agg(markets=("market_id", "nunique"), records=("price_local", "size"),
                       commodities=("commodity", "nunique"))
                  .reset_index())
    coverage.to_csv(CLEAN / "coverage.csv", index=False)

    months = pd.date_range("1990-01-01", "2026-12-01", freq="MS")
    dates = pd.DataFrame({"month": months})
    dates["year"] = dates.month.dt.year
    dates["month_num"] = dates.month.dt.month
    dates["month_name"] = dates.month.dt.strftime("%b")
    dates["month_label"] = dates.month.dt.strftime("%b %Y")
    # Nigeria's naira was floated in June 2023 (devaluation); used to mark charts.
    dates["period"] = np.where(dates.month >= "2023-06-01", "After devaluation (Jun 2023+)", "Before devaluation")
    dates.to_csv(CLEAN / "dates.csv", index=False)

    countries = d.groupby("country").currency.first().reset_index()
    countries.to_csv(CLEAN / "countries.csv", index=False)

    assert len(prices) == n_raw, "row count changed during cleaning"
    print(f"prices.csv       {len(prices):>7} rows  (raw {n_raw})")
    print(f"markets.csv      {len(markets):>7} rows")
    print(f"commodities.csv  {len(commodities):>7} rows")
    print(f"fx_monthly.csv   {len(fx):>7} rows")
    print(f"coverage.csv     {len(coverage):>7} rows")
    print(prices.exclude_reason.value_counts().to_string())
    print("incomplete months:", sorted(partial))


if __name__ == "__main__":
    main()
