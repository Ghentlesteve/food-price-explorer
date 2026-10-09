"""Generate the Power BI report pages (legacy report.json) and theme for food-price-explorer.

Run from the repo root:  python scripts/make_report.py
Power BI Desktop must be closed while this runs; reopen powerbi/food-price-explorer.pbip afterwards.
"""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "powerbi" / "food-price-explorer.Report"
THEME_NAME = "FoodPriceExplorer.json"

# ---------------------------------------------------------------- palette
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#4A3AA7", "#E34948")
PAGE_BG, CARD_BG, BORDER = "#F4F3EF", "#FFFFFF", "#E4E2DC"
INK, INK2, INK3 = "#0B0B0B", "#52514E", "#8A8984"

THEME = {
    "name": "Food Price Explorer",
    "dataColors": [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED],
    "foreground": INK, "foregroundNeutralSecondary": INK2, "foregroundNeutralTertiary": INK3,
    "background": CARD_BG, "backgroundLight": "#F0EFEC", "backgroundNeutral": BORDER,
    "tableAccent": BLUE, "good": "#0CA30C", "neutral": "#FAB219", "bad": "#D03B3B",
    "maximum": "#1C5CAB", "center": "#86B6EF", "minimum": "#F0EFEC",
    "textClasses": {
        "callout": {"fontSize": 26, "fontFace": "Segoe UI Semibold", "color": INK},
        "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
        "header": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
        "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": INK2},
    },
    "visualStyles": {
        "*": {"*": {
            "background": [{"show": True, "color": {"solid": {"color": CARD_BG}}, "transparency": 0}],
            "border": [{"show": True, "color": {"solid": {"color": BORDER}}, "radius": 8}],
            "dropShadow": [{"show": False}],
            "padding": [{"top": 10, "bottom": 10, "left": 14, "right": 14}],
            "title": [{"show": True, "fontSize": 12, "fontColor": {"solid": {"color": INK}},
                       "fontFamily": "Segoe UI Semibold"}],
            "categoryAxis": [{"gridlineShow": False, "labelColor": {"solid": {"color": INK2}},
                              "showAxisTitle": False}],
            "valueAxis": [{"gridlineShow": True, "gridlineColor": {"solid": {"color": "#ECEAE4"}},
                           "gridlineStyle": "solid", "labelColor": {"solid": {"color": INK2}},
                           "showAxisTitle": False}],
            "legend": [{"show": True, "position": "Top", "labelColor": {"solid": {"color": INK2}},
                        "fontSize": 9}],
        }},
        "page": {"*": {
            "background": [{"color": {"solid": {"color": PAGE_BG}}, "transparency": 0}],
            "outspace": [{"color": {"solid": {"color": PAGE_BG}}, "transparency": 0}],
        }},
        "lineChart": {"*": {"lineStyles": [{"strokeWidth": 2, "showMarker": False}]}},
        "textbox": {"*": {"background": [{"show": False}], "border": [{"show": False}],
                          "padding": [{"top": 0, "bottom": 0, "left": 0, "right": 0}]}},
        "slicer": {"*": {"header": [{"show": True, "fontColor": {"solid": {"color": INK2}},
                                     "textSize": 9}],
                         "items": [{"fontColor": {"solid": {"color": INK}}, "textSize": 10}]}},
        "card": {"*": {"labels": [{"color": {"solid": {"color": INK}}, "fontSize": 26}],
                       "categoryLabels": [{"show": False}]}},
        "tableEx": {"*": {"grid": [{"gridVertical": False, "rowPadding": 6}],
                          "columnHeaders": [{"fontColor": {"solid": {"color": INK2}}}]}},
        "pivotTable": {"*": {"grid": [{"gridVertical": False, "rowPadding": 4}],
                             "columnHeaders": [{"fontColor": {"solid": {"color": INK2}}}]}},
    },
}

# ---------------------------------------------------------------- query helpers
ALIASES = {"prices": "p", "markets": "m", "commodities": "c", "fx_monthly": "f",
           "dates": "d", "countries": "n"}


def lit(v):
    if isinstance(v, bool):
        return {"expr": {"Literal": {"Value": "true" if v else "false"}}}
    if isinstance(v, (int, float)):
        return {"expr": {"Literal": {"Value": f"{v}D"}}}
    return {"expr": {"Literal": {"Value": "'" + str(v).replace("'", "''") + "'"}}}


def measure_expr(table, name):
    return {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}}


def color(hex_):
    return {"solid": {"color": lit(hex_)}}


class Field:
    def __init__(self, table, prop, kind="col", agg=None):
        self.table, self.prop, self.kind, self.agg = table, prop, kind, agg

    @property
    def ref(self):
        if self.agg is not None:
            return f"{['Sum','Avg','Count','Min','Max'][self.agg]}({self.table}.{self.prop})"
        return f"{self.table}.{self.prop}"

    def select(self):
        src = {"Expression": {"SourceRef": {"Source": ALIASES[self.table]}}, "Property": self.prop}
        if self.kind == "measure":
            body = {"Measure": src}
        else:
            body = {"Column": src}
            if self.agg is not None:
                body = {"Aggregation": {"Expression": {"Column": src}, "Function": self.agg}}
        return {**body, "Name": self.ref}

    def expr(self):
        src = {"Expression": {"SourceRef": {"Source": ALIASES[self.table]}}, "Property": self.prop}
        return {"Measure": src} if self.kind == "measure" else {"Column": src}


def C(t, p, agg=None):
    return Field(t, p, "col", agg)


def M(t, p):
    return Field(t, p, "measure")


def literal_value(v):
    if isinstance(v, int):
        return f"{v}L"
    return "'" + str(v).replace("'", "''") + "'"


def in_filter(field, values, name=None):
    """Categorical 'In' filter definition (used by filters and slicer defaults)."""
    a = ALIASES[field.table]
    return {
        "Version": 2,
        "From": [{"Name": a, "Entity": field.table, "Type": 0}],
        "Where": [{"Condition": {"In": {
            "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": a}}, "Property": field.prop}}],
            "Values": [[{"Literal": {"Value": literal_value(v)}}] for v in values]}}}],
    }


def filter_entry(field, values):
    h = hashlib.md5(f"{field.ref}{values}".encode()).hexdigest()[:20]
    return {
        "name": "Filter" + h,
        "expression": {"Column": {"Expression": {"SourceRef": {"Entity": field.table}}, "Property": field.prop}},
        "filter": in_filter(field, values),
        "type": "Categorical",
        "howCreated": 1,
        "isHiddenInViewMode": False,
    }


_counter = [0]


def vid(prefix):
    _counter[0] += 1
    return hashlib.md5(f"{prefix}{_counter[0]}".encode()).hexdigest()[:20]


def visual(vtype, x, y, w, h, projections=None, objects=None, vc=None, title=None, sort=None,
           filters=None, name=None, extra=None, display_names=None, z=None):
    projections = projections or {}
    fields, seen = [], set()
    for role, items in projections.items():
        for f in items:
            if f.ref not in seen:
                seen.add(f.ref)
                fields.append(f)
    tables = []
    for f in fields:
        if f.table not in tables:
            tables.append(f.table)
    if sort:
        for f, _ in sort:
            if f.table not in tables:
                tables.append(f.table)
    if vtype == "lineChart":
        objects = {"legend": [{"properties": {"showTitle": lit(False)}}], **(objects or {})}
    sv = {"visualType": vtype}
    if fields:
        sv["projections"] = {role: [{"queryRef": f.ref, **({"active": True} if vtype == "slicer" else {})}
                                    for f in items] for role, items in projections.items()}
        pq = {"Version": 2,
              "From": [{"Name": ALIASES[t], "Entity": t, "Type": 0} for t in tables],
              "Select": [f.select() for f in fields]}
        if sort:
            pq["OrderBy"] = [{"Direction": d, "Expression": f.expr()} for f, d in sort]
        sv["prototypeQuery"] = pq
    if display_names:
        sv["columnProperties"] = {f.ref: {"displayName": dn} for f, dn in display_names}
    sv["drillFilterOtherVisuals"] = True
    if objects:
        sv["objects"] = objects
    vco = dict(vc or {})
    if title is not None:
        if isinstance(title, Field):
            vco["title"] = [{"properties": {"show": lit(True), "text": measure_expr(title.table, title.prop)}}]
        elif title is False:
            vco["title"] = [{"properties": {"show": lit(False)}}]
        else:
            vco["title"] = [{"properties": {"show": lit(True), "text": lit(title)}}]
    if vco:
        sv["vcObjects"] = vco
    if extra:
        sv.update(extra)
    name = name or vid(vtype)
    zz = z if z is not None else _counter[0] * 100
    cfg = {"name": name,
           "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": zz, "width": w, "height": h,
                                               "tabOrder": zz}}],
           "singleVisual": sv}
    return {"x": x, "y": y, "z": zz, "width": w, "height": h,
            "config": json.dumps(cfg, ensure_ascii=False),
            "filters": json.dumps(filters or [], ensure_ascii=False),
            "_name": name}


def textbox(x, y, w, h, paragraphs):
    """paragraphs: list of list of (text, style dict)."""
    paras = [{"textRuns": [{"value": t, "textStyle": s} for t, s in runs]} for runs in paragraphs]
    return visual("textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": paras}}]})


def header(title, subtitle):
    return textbox(24, 14, 740, 70, [
        [(title, {"fontFamily": "Segoe UI Semibold", "fontSize": "20pt", "color": INK})],
        [(subtitle, {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": INK2})],
    ])


def slicer(field, x, y, w, h, title, mode="Dropdown", single=True, default=None, sync=None):
    objects = {"data": [{"properties": {"mode": lit(mode)}}],
               "header": [{"properties": {"show": lit(True), "text": lit(title)}}]}
    if mode != "Between":
        objects["selection"] = [{"properties": {"singleSelect": lit(single),
                                                "strictSingleSelect": lit(single)}}]
    if default is not None:
        objects["general"] = [{"properties": {"filter": {"filter": in_filter(field, default)}}}]
    extra = {"syncGroup": {"groupName": sync, "fieldChanges": True, "filterChanges": True}} if sync else None
    return visual("slicer", x, y, w, h, projections={"Values": [field]}, objects=objects, title=False,
                  extra=extra, vc={"padding": [{"properties": {"top": lit(4), "bottom": lit(4)}}]})


def card(measure, x, y, w, h, title, fmt_units=True):
    objects = {"labels": [{"properties": {"fontSize": lit(26), **({"labelDisplayUnits": lit(1)} if fmt_units else {})}}],
               "categoryLabels": [{"properties": {"show": lit(False)}}]}
    return visual("card", x, y, w, h, projections={"Values": [measure]}, objects=objects, title=title)


def series_colors(field, mapping):
    return [{"properties": {"fill": color(c)},
             "selector": {"data": [{"scopeId": {"Comparison": {
                 "ComparisonKind": 0,
                 "Left": {"Column": {"Expression": {"SourceRef": {"Entity": field.table}}, "Property": field.prop}},
                 "Right": {"Literal": {"Value": literal_value(v)}}}}}]}} for v, c in mapping.items()]


TOOLTIP_PAGE = "a1f0000000000000tip1"


def tooltip_vc():
    return {"visualTooltip": [{"properties": {"type": lit("ReportPage"), "section": lit(TOOLTIP_PAGE)}}]}


def section(display, name, visuals, filters=None, no_filter_pairs=(), hidden=False, tooltip=False):
    cfg = {}
    if no_filter_pairs:
        cfg["relationships"] = [{"source": s, "target": t, "type": 3} for s, t in no_filter_pairs]
    if hidden:
        cfg["visibility"] = 1
    if tooltip:
        cfg["objects"] = {
            "pageInformation": [{"properties": {"pageInformationType": lit("Tooltip")}}],
            "background": [{"properties": {"color": {"solid": {"color": lit(CARD_BG)}}, "transparency": lit(0)}}],
        }
        cfg["type"] = 1  # 1 = tooltip page
    return {
        "config": json.dumps(cfg),
        "displayName": display,
        "displayOption": 3 if tooltip else 1,
        "filters": json.dumps(filters or [], ensure_ascii=False),
        "height": 240.0 if tooltip else 720.0,
        "name": name,
        "visualContainers": [{k: v for k, v in vc.items() if k != "_name"} for vc in visuals],
        "width": 320.0 if tooltip else 1280.0,
    }


# ---------------------------------------------------------------- fields
group = C("prices", "commodity_group")
month = C("dates", "month")
year = C("dates", "year")
period = C("dates", "period")
m_zone, m_state, m_market, m_country = (C("markets", p) for p in ("zone", "state", "market", "country"))
country = C("countries", "country")

NE_STAPLES = ["Rice (local)", "Rice (imported)", "Beans", "Cowpeas", "Millet", "Sorghum", "Yam",
              "Maize flour", "Palm oil", "Tomatoes", "Onions", "Sugar", "Eggs", "Beef"]
SHARED = ["Millet", "Sorghum", "Rice (imported)", "Cowpeas"]
YEARS_2015 = list(range(2015, 2027))
YEARS_2020 = list(range(2020, 2027))
italic_note = {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": INK3}

# ---------------------------------------------------------------- page 1
p1 = []
p1.append(header("What happened to food prices in North East Nigeria?",
                 "Median retail price across WFP-monitored markets in Borno, Yobe and Adamawa. "
                 "The naira was devalued in June 2023."))
s1 = slicer(group, 780, 18, 180, 62, "Food", default=["Rice (local)"], sync="food")
s2 = slicer(month, 972, 18, 284, 62, "Months", mode="Between", sync="months")
p1 += [s1, s2]
cw, cg, cy = 296, 16, 96
p1.append(card(M("prices", "Price Latest"), 24, cy, cw, 96, M("prices", "KPI Latest Title")))
p1.append(card(M("prices", "Change 12M %"), 24 + (cw + cg), cy, cw, 96, "Change over the last 12 months",
               fmt_units=False))
p1.append(card(M("prices", "Change Since 2020 %"), 24 + 2 * (cw + cg), cy, cw, 96, "Change since January 2020",
               fmt_units=False))
p1.append(card(M("prices", "Markets Latest"), 24 + 3 * (cw + cg), cy, cw, 96, "Markets reporting, latest month"))
trend = visual("lineChart", 24, 208, 740, 470,
               projections={"Category": [month], "Y": [M("prices", "Median Price")], "Series": [period]},
               objects={"dataPoint": series_colors(period, {"Before devaluation": BLUE,
                                                            "After devaluation (Jun 2023+)": ORANGE})},
               title=M("prices", "Trend Title"))
p1.append(trend)
bar = visual("barChart", 780, 208, 476, 470,
             projections={"Category": [group], "Y": [M("prices", "Change Since 2020 %")]},
             objects={"labels": [{"properties": {"show": lit(True), "color": color(INK2)}}],
                      "dataPoint": [{"properties": {"fill": color(BLUE)}}],
                      "valueAxis": [{"properties": {"show": lit(False), "gridlineShow": lit(False)}}]},
             title="Price change since January 2020, by food",
             sort=[(M("prices", "Change Since 2020 %"), 2)],
             filters=[filter_entry(group, NE_STAPLES)])
p1.append(bar)
p1.append(textbox(24, 686, 1232, 24, [[(
    "Source: WFP market price monitoring via HDX. Retail prices only, per kg, litre or piece. Outliers, "
    "pack-size breaks and the incomplete month (Sep 2026) are left out; see Data coverage.", italic_note)]]))
page1 = section("Overview", "a1f0000000000000p001", p1,
                filters=[filter_entry(m_zone, ["North East"])],
                no_filter_pairs=[(s1["_name"], bar["_name"])])

# ---------------------------------------------------------------- page 2
p2 = []
p2.append(header("Where is food most expensive?",
                 "Markets in Borno, Yobe and Adamawa, latest month with data. "
                 "Bubble size shows the price in each market."))
s3 = slicer(group, 780, 18, 180, 62, "Food", default=["Rice (local)"], sync="food")
s4 = slicer(month, 972, 18, 284, 62, "Months", mode="Between", sync="months")
p2 += [s3, s4]
p2.append(card(M("prices", "Market Min Latest"), 24, cy, cw, 96, "Cheapest market (₦)"))
p2.append(card(M("prices", "Market Max Latest"), 24 + (cw + cg), cy, cw, 96, "Most expensive market (₦)"))
p2.append(card(M("prices", "Market Spread Latest %"), 24 + 2 * (cw + cg), cy, cw, 96,
               "Gap, most vs least expensive", fmt_units=False))
p2.append(card(M("prices", "Markets Latest"), 24 + 3 * (cw + cg), cy, cw, 96, "Markets reporting, latest month"))
p2.append(visual("azureMap", 24, 208, 560, 470,
                 projections={"Category": [m_market],
                              "Y": [C("markets", "latitude", 1)], "X": [C("markets", "longitude", 1)],
                              "Series": [m_state], "Size": [M("prices", "Market Price Latest")]},
                 vc=tooltip_vc(), title=M("prices", "Map Title")))
p2.append(visual("lineChart", 600, 208, 656, 228,
                 projections={"Category": [month], "Y": [M("prices", "Median Price")], "Series": [m_state]},
                 title="Median price by state (₦)"))
p2.append(visual("barChart", 600, 450, 656, 228,
                 projections={"Category": [m_market], "Y": [M("prices", "Market Price Latest")],
                              "Series": [m_state]},
                 sort=[(M("prices", "Market Price Latest"), 2)],
                 objects={"legend": [{"properties": {"show": lit(False)}}]}, vc=tooltip_vc(),
                 title="Price in each market, latest month (₦), coloured by state"))
p2.append(textbox(24, 686, 1232, 24, [[(
    "Each market's price is for the latest month in the selection, so markets that stopped reporting drop out "
    "rather than showing an old price.", italic_note)]]))
page2 = section("North East markets", "a1f0000000000000p002", p2,
                filters=[filter_entry(m_zone, ["North East"])])

# ---------------------------------------------------------------- page 3
p3 = []
p3.append(header("Nigeria vs Niger: is it the food or the currency?",
                 "Same staples, indexed to January 2020 = 100. Both countries' prices are from WFP market monitoring."))
s5 = slicer(group, 1046, 18, 210, 62, "Food", default=["Millet"])
p3.append(s5)
p3.append(visual("tableEx", 24, 96, 1232, 122,
                 projections={"Values": [country, M("prices", "Latest Month Label"),
                                         M("prices", "Change Since 2020 %"),
                                         M("prices", "Change Since 2020 USD %"),
                                         M("fx_monthly", "FX Change Since 2020 %")]},
                 display_names=[(M("prices", "Latest Month Label"), "Latest month"),
                                (M("prices", "Change Since 2020 %"), "Price change since Jan 2020, local currency"),
                                (M("prices", "Change Since 2020 USD %"), "Price change since Jan 2020, in USD"),
                                (M("fx_monthly", "FX Change Since 2020 %"), "Local currency per USD, change since Jan 2020"),
                                (country, "Country")],
                 objects={"total": [{"properties": {"totals": lit(False)}}]},
                title=False))
w3 = 400
p3.append(visual("lineChart", 24, 234, w3, 444,
                 projections={"Category": [month], "Y": [M("prices", "Price Index (Jan 2020 = 100)")],
                              "Series": [country]},
                 title="Price in local currency (Jan 2020 = 100)"))
p3.append(visual("lineChart", 24 + w3 + 16, 234, w3, 444,
                 projections={"Category": [month], "Y": [M("prices", "Price Index USD (Jan 2020 = 100)")],
                              "Series": [country]},
                 title="Price in US dollars (Jan 2020 = 100)"))
p3.append(visual("lineChart", 24 + 2 * (w3 + 16), 234, w3, 444,
                 projections={"Category": [month], "Y": [M("fx_monthly", "FX Index (Jan 2020 = 100)")],
                              "Series": [country]},
                 title="Local currency per US dollar (Jan 2020 = 100)"))
p3.append(textbox(24, 686, 1232, 24, [[(
    "Nigeria: North East markets only. USD prices use the exchange rate WFP applied each month. "
    "Niger uses the CFA franc (XOF), pegged to the euro.", italic_note)]]))
page3 = section("Nigeria vs Niger", "a1f0000000000000p003", p3,
                filters=[filter_entry(group, SHARED), filter_entry(year, YEARS_2020),
                         filter_entry(m_zone, ["North East", "Niger"])])

# ---------------------------------------------------------------- page 4
p4 = []
p4.append(header("Where the data comes from",
                 "WFP monitors Nigerian markets mainly where it runs humanitarian operations."))
p4.append(textbox(24, 100, 380, 560, [
    [("What the data covers", {"fontFamily": "Segoe UI Semibold", "fontSize": "12pt", "color": INK})],
    [("", {"fontSize": "6pt"})],
    [("North East (Borno, Yobe, Adamawa): ", {"fontFamily": "Segoe UI Semibold", "fontSize": "10pt", "color": INK}),
     ("monitored through 2026. Gombe stops in January 2023.", {"fontSize": "10pt", "color": INK2})],
    [("", {"fontSize": "6pt"})],
    [("North West, South West, South East: ", {"fontFamily": "Segoe UI Semibold", "fontSize": "10pt", "color": INK}),
     ("monitored until January 2023, then stop.", {"fontSize": "10pt", "color": INK2})],
    [("", {"fontSize": "6pt"})],
    [("North Central, South South: ", {"fontFamily": "Segoe UI Semibold", "fontSize": "10pt", "color": INK}),
     ("no price data in this dataset.", {"fontSize": "10pt", "color": INK2})],
    [("", {"fontSize": "6pt"})],
    [("So the dashboard focuses on the North East. It is not a national price index.",
      {"fontSize": "10pt", "color": INK2})],
    [("", {"fontSize": "6pt"})],
    [("Data preparation", {"fontFamily": "Segoe UI Semibold", "fontSize": "12pt", "color": INK})],
    [("", {"fontSize": "6pt"})],
    [("Prices are converted to a common unit (per kg, litre or piece) and food names are harmonised "
      "across the two countries. 672 of 160,117 records are left out of the medians: 333 outliers (more "
      "than 5x or less than 0.2x the monthly median for the same food), 245 in months where a whole series "
      "jumps or falls more than 3x, which points to a pack-size change in the source (sugar in Oct-Nov 2024 "
      "and Jul-Sep 2026), and 94 from September 2026, when only 4 markets had reported.",
      {"fontSize": "10pt", "color": INK2})],
]))
p4.append(visual("lineChart", 420, 96, 836, 280,
                 projections={"Category": [month], "Y": [M("prices", "Markets Reporting")], "Series": [m_zone]},
                 title="Nigerian markets reporting retail prices each month, by zone"))
p4.append(visual("pivotTable", 420, 392, 836, 286,
                 projections={"Rows": [m_zone, m_state], "Columns": [year],
                              "Values": [M("prices", "Markets Reporting")]},
                 objects={"values": [{"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
                     "Input": {"Measure": {"Expression": {"SourceRef": {"Entity": "prices"}},
                                           "Property": "Markets Reporting"}},
                     "FillRule": {"linearGradient2": {
                         "min": {"color": {"Literal": {"Value": "'#F0EFEC'"}}},
                         "max": {"color": {"Literal": {"Value": "'#86B6EF'"}}},
                         "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}}}}}}}}}},
                     "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                                  "metadata": "prices.Markets Reporting"}}],
                          "subTotals": [{"properties": {"rowSubtotals": lit(False)}}]},
                 title="Markets reporting per year (Nigeria)"))
page4 = section("Data coverage", "a1f0000000000000p004", p4,
                filters=[filter_entry(m_country, ["Nigeria"]), filter_entry(year, YEARS_2015)])

# ---------------------------------------------------------------- tooltip page (hidden)
tip = [
    visual("card", 0, 0, 320, 70, projections={"Values": [M("prices", "Market Price Latest")]},
           objects={"labels": [{"properties": {"fontSize": lit(20), "labelDisplayUnits": lit(1)}}],
                    "categoryLabels": [{"properties": {"show": lit(False)}}]},
           vc={"border": [{"properties": {"show": lit(False)}}]}, title=M("prices", "Tooltip Title")),
    visual("lineChart", 0, 70, 320, 170,
           projections={"Category": [month], "Y": [M("prices", "Median Price")]},
           objects={"dataPoint": [{"properties": {"fill": color(BLUE)}}]},
           vc={"border": [{"properties": {"show": lit(False)}}]}, title="Price trend in this market (₦)"),
]
page_tip = section("Market tooltip", TOOLTIP_PAGE, tip, hidden=True, tooltip=True)

# ---------------------------------------------------------------- write
rj_path = REPORT / "report.json"
rj = json.loads(rj_path.read_text(encoding="utf-8"))
cfg = json.loads(rj["config"])
cfg["themeCollection"]["customTheme"] = {"name": THEME_NAME, "type": 1, "version": "5.65"}
cfg["activeSectionIndex"] = 0
rj["config"] = json.dumps(cfg)
rj["resourcePackages"] = [p for p in rj["resourcePackages"]
                          if p["resourcePackage"]["name"] != "RegisteredResources"]

rj["resourcePackages"].append({"resourcePackage": {
    "disabled": False, "items": [{"name": THEME_NAME, "path": THEME_NAME, "type": 201}],
    "name": "RegisteredResources", "type": 1}})
rj["sections"] = [page1, page2, page3, page4, page_tip]
rj_path.write_text(json.dumps(rj, indent=2, ensure_ascii=False), encoding="utf-8")

theme_dir = REPORT / "StaticResources" / "RegisteredResources"
theme_dir.mkdir(parents=True, exist_ok=True)
(theme_dir / THEME_NAME).write_text(json.dumps(THEME, indent=2), encoding="utf-8")
print("wrote", rj_path, "with", sum(len(s["visualContainers"]) for s in rj["sections"]), "visuals")
