"""Append report-support measures to the PBIP semantic model (idempotent).

Run from the repo root with Power BI Desktop closed:  python scripts/add_measures.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "powerbi" / "food-price-explorer.SemanticModel" / "definition" / "tables"

NEW = {
    "prices": [
        ("Unit Label", 'CALCULATE ( MAX ( prices[std_unit] ), prices[is_main_unit] = TRUE () )', None),
        ("Trend Title",
         'SELECTEDVALUE ( prices[commodity_group], "Selected food" ) & ": median retail price, ₦ per " & [Unit Label]',
         None),
        ("KPI Latest Title", '"Latest price, ₦ per " & [Unit Label] & " (" & [Latest Month Label] & ")"', None),
        ("Markets Latest",
         'VAR lm = [Latest Month] RETURN CALCULATE ( [Markets Reporting], REMOVEFILTERS ( dates ), dates[month] = lm )',
         "#,0"),
        ("Market Price Latest",
         'VAR lm = CALCULATE ( [Latest Month], ALLSELECTED ( markets ) ) '
         'RETURN CALCULATE ( [Median Price], REMOVEFILTERS ( dates ), dates[month] = lm )', "#,0"),
        ("Market Max Latest", 'MAXX ( VALUES ( markets[market_id] ), [Market Price Latest] )', "#,0"),
        ("Market Min Latest", 'MINX ( VALUES ( markets[market_id] ), [Market Price Latest] )', "#,0"),
        ("Market Spread Latest %",
         'DIVIDE ( [Market Max Latest] - [Market Min Latest], [Market Min Latest] )', "0%"),
        ("Map Title",
         'SELECTEDVALUE ( prices[commodity_group], "Selected food" ) & " by market, ₦ per " & [Unit Label] '
         '& " (" & FORMAT ( CALCULATE ( [Latest Month], ALLSELECTED ( markets ) ), "mmm yyyy" ) & ")"', None),
        ("Tooltip Title",
         'SELECTEDVALUE ( markets[market], "Market" ) & ", " & SELECTEDVALUE ( markets[state] ) '
         '& ": ₦ per " & [Unit Label] & ", " & FORMAT ( CALCULATE ( [Latest Month], ALLSELECTED ( markets ) ), "mmm yyyy" )',
         None),
        ("Change Since 2020 USD %",
         'VAR lm = [Latest Month] '
         'VAR a = CALCULATE ( [Median Price USD], REMOVEFILTERS ( dates ), dates[month] = lm ) '
         'VAR b = CALCULATE ( [Median Price USD], REMOVEFILTERS ( dates ), dates[month] = DATE ( 2020, 1, 1 ) ) '
         'RETURN DIVIDE ( a - b, b )', "+0%;-0%;0%"),
    ],
    "fx_monthly": [
        ("FX Change Since 2020 %",
         'VAR lm = [Latest Month] '
         'VAR a = CALCULATE ( [Exchange Rate (per USD)], REMOVEFILTERS ( dates ), dates[month] = lm ) '
         'VAR b = CALCULATE ( [Exchange Rate (per USD)], REMOVEFILTERS ( dates ), dates[month] = DATE ( 2020, 1, 1 ) ) '
         'RETURN DIVIDE ( a - b, b )', "+0%;-0%;0%"),
    ],
}

for table, measures in NEW.items():
    path = TABLES / f"{table}.tmdl"
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    first = next(i for i, l in enumerate(lines) if l.startswith(("\tmeasure ", "\tcolumn ")))
    block = []
    for name, expr, fmt in measures:
        if f"measure '{name}'" in text or f"measure {name} " in text:
            continue
        block.append(f"\tmeasure '{name}' = {expr}")
        if fmt:
            block.append(f"\t\tformatString: {fmt}")
        block.append("")
    if block:
        lines[first:first] = block
        path.write_text("\n".join(lines), encoding="utf-8")
    print(table, "added", sum(1 for b in block if b.startswith("\tmeasure")))
