"""Generate powerbi/model.tmdl: the Power BI data model (tables, relationships, measures).

Paste the file into Power BI Desktop's TMDL view and click Apply, then Refresh.
Change the DataFolder parameter (Transform data > Edit parameters) to point at your copy of data/clean/.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
WIN_FOLDER = r"C:\Users\Kwenev Steve\Documents\Web\Advanced Dashboards\food-price-explorer\data\clean" + "\\"

TABLES = ["prices", "markets", "commodities", "fx_monthly", "dates", "countries"]
DATE_COLS = {"month", "first_month", "last_month"}
T = "\t"


def kinds(df):
    out = {}
    for c, dt in df.dtypes.items():
        if c in DATE_COLS:
            out[c] = ("dateTime", "type date")
        elif dt == bool:
            out[c] = ("boolean", "type logical")
        elif str(dt).startswith("int"):
            out[c] = ("int64", "Int64.Type")
        elif str(dt).startswith("float"):
            out[c] = ("double", "type number")
        else:
            out[c] = ("string", "type text")
    return out


MEASURES = {
    "prices": [
        ("Median Price", 'CALCULATE ( MEDIAN ( prices[price_per_unit_local] ), prices[exclude] = FALSE (), prices[is_main_unit] = TRUE (), prices[pricetype] = "Retail" )', "#,0"),
        ("Median Price USD", 'CALCULATE ( MEDIAN ( prices[price_per_unit_usd] ), prices[exclude] = FALSE (), prices[is_main_unit] = TRUE (), prices[pricetype] = "Retail" )', "$#,0.00"),
        ("Latest Month", "CALCULATE ( MAX ( prices[month] ), ALLSELECTED ( dates ), prices[exclude] = FALSE () )", "mmm yyyy"),
        ("Price Latest", "VAR lm = [Latest Month] RETURN CALCULATE ( [Median Price], REMOVEFILTERS ( dates ), dates[month] = lm )", "#,0"),
        ("Price 12M Ago", "VAR lm = [Latest Month] RETURN CALCULATE ( [Median Price], REMOVEFILTERS ( dates ), dates[month] = EDATE ( lm, -12 ) )", "#,0"),
        ("Change 12M %", "VAR a = [Price 12M Ago] RETURN DIVIDE ( [Price Latest] - a, a )", "+0%;-0%;0%"),
        ("Price Jan 2020", "CALCULATE ( [Median Price], REMOVEFILTERS ( dates ), dates[month] = DATE ( 2020, 1, 1 ) )", "#,0"),
        ("Change Since 2020 %", "DIVIDE ( [Price Latest] - [Price Jan 2020], [Price Jan 2020] )", "+0%;-0%;0%"),
        ("Markets Reporting", "CALCULATE ( DISTINCTCOUNT ( prices[market_id] ), prices[pricetype] = \"Retail\" )", "#,0"),
        ("Records", "COUNTROWS ( prices )", "#,0"),
        ("Market Max Price", "MAXX ( VALUES ( markets[market_id] ), [Median Price] )", "#,0"),
        ("Market Min Price", "MINX ( VALUES ( markets[market_id] ), [Median Price] )", "#,0"),
        ("Market Spread %", "DIVIDE ( [Market Max Price] - [Market Min Price], [Market Min Price] )", "0%"),
        ("Price Index (Jan 2020 = 100)", "DIVIDE ( [Median Price], [Price Jan 2020] ) * 100", "#,0"),
        ("Price Index USD (Jan 2020 = 100)", "DIVIDE ( [Median Price USD], CALCULATE ( [Median Price USD], REMOVEFILTERS ( dates ), dates[month] = DATE ( 2020, 1, 1 ) ) ) * 100", "#,0"),
        ("Latest Month Label", 'FORMAT ( [Latest Month], "mmm yyyy" )', None),
    ],
    "fx_monthly": [
        ("Exchange Rate (per USD)", "AVERAGE ( fx_monthly[local_per_usd] )", "#,0"),
        ("FX Index (Jan 2020 = 100)", "DIVIDE ( [Exchange Rate (per USD)], CALCULATE ( [Exchange Rate (per USD)], REMOVEFILTERS ( dates ), dates[month] = DATE ( 2020, 1, 1 ) ) ) * 100", "#,0"),
    ],
}

RELATIONSHIPS = [
    ("prices", "market_id", "markets", "market_id"),
    ("prices", "commodity", "commodities", "commodity"),
    ("prices", "month", "dates", "month"),
    ("prices", "country", "countries", "country"),
    ("fx_monthly", "month", "dates", "month"),
    ("fx_monthly", "country", "countries", "country"),
]


def q(name):
    return f"'{name}'" if any(ch in name for ch in " ()%=/-") else name


def main():
    lines = ["createOrReplace", ""]
    lines += [f'{T}expression DataFolder = "{WIN_FOLDER}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]', ""]
    for t in TABLES:
        df = pd.read_csv(CLEAN / f"{t}.csv", nrows=2000)
        k = kinds(df)
        lines.append(f"{T}table {t}")
        lines.append("")
        for name, expr, fmt in MEASURES.get(t, []):
            lines.append(f"{T*2}measure {q(name)} = {expr}")
            if fmt:
                lines.append(f'{T*3}formatString: {fmt}')
            lines.append("")
        for c, (tm, _) in k.items():
            lines.append(f"{T*2}column {c}")
            lines.append(f"{T*3}dataType: {tm}")
            if tm == "dateTime":
                lines.append(f"{T*3}formatString: mmm yyyy")
            if tm in ("int64", "double") or c.endswith("_id"):
                lines.append(f"{T*3}summarizeBy: none" if (c.endswith("_id") or c in ("year", "month_num", "latitude", "longitude")) else f"{T*3}summarizeBy: sum")
            else:
                lines.append(f"{T*3}summarizeBy: none")
            lines.append(f"{T*3}sourceColumn: {c}")
            lines.append("")
        types = ", ".join(f'{{"{c}", {m}}}' for c, (_, m) in k.items())
        lines += [
            f"{T*2}partition {t} = m",
            f"{T*3}mode: import",
            f"{T*3}source =",
            f"{T*5}let",
            f'{T*6}Source = Csv.Document(File.Contents(DataFolder & "{t}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
            f"{T*6}Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
            f'{T*6}Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
            f"{T*5}in",
            f"{T*6}Typed",
            "",
        ]
    for i, (ft, fc, tt, tc) in enumerate(RELATIONSHIPS, 1):
        lines += [f"{T}relationship rel_{ft}_{tt}", f"{T*2}fromColumn: {ft}.{fc}", f"{T*2}toColumn: {tt}.{tc}", ""]
    out = ROOT / "powerbi" / "model.tmdl"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out, len(lines), "lines")


if __name__ == "__main__":
    main()
