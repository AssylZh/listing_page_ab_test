"""Build ab_test_results.xlsx

Run: python make_excel.py
"""
import sqlite3

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

BLUE = Font(name="Arial", color="0000FF")
BOLD = Font(name="Arial", bold=True)
NORMAL = Font(name="Arial")
HEADER = Font(name="Arial", bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
PFMT = "[<0.0001]\"< 0.0001\";0.0000"
NOTE = Font(name="Arial", italic=True, color="595959", size=9)

# ---- SQL: get the counts ----
con = sqlite3.connect(":memory:")
pd.read_csv("data/experiment_users.csv").to_sql("users", con, index=False)
overall = pd.read_sql("""
    SELECT variant, COUNT(*) AS users, SUM(contacted_agent) AS contacted
    FROM users GROUP BY variant""", con).set_index("variant")
device = pd.read_sql("""
    SELECT device, variant, COUNT(*) AS users, SUM(contacted_agent) AS contacted
    FROM users GROUP BY device, variant""", con)

wb = Workbook()


def header_row(ws, row, labels):
    for i, text in enumerate(labels, start=1):
        c = ws.cell(row=row, column=i, value=text)
        c.font, c.fill = HEADER, HEADER_FILL


def write(ws, ref, value, font=NORMAL, fmt=None, fill=None):
    ws[ref] = value
    ws[ref].font = font
    if fmt:
        ws[ref].number_format = fmt
    if fill:
        ws[ref].fill = fill


# ---- Tab 1: Results ----
ws = wb.active
ws.title = "Results"
write(ws, "A1", "A/B test result: contact-agent rate", Font(name="Arial", bold=True, size=14))
write(ws, "A2", "Blue cells = data from SQL (edit to test other numbers). Black = formulas.", NOTE)
header_row(ws, 4, ["", "Control", "Treatment"])
write(ws, "A5", "Users")
write(ws, "A6", "Contacted an agent")
for col, v in (("B", "control"), ("C", "treatment")):
    write(ws, f"{col}5", int(overall.loc[v, "users"]), BLUE, "#,##0", INPUT_FILL)
    write(ws, f"{col}6", int(overall.loc[v, "contacted"]), BLUE, "#,##0", INPUT_FILL)
write(ws, "A7", "Contact rate", BOLD)
write(ws, "B7", "=B6/B5", BOLD, "0.00%")
write(ws, "C7", "=C6/C5", BOLD, "0.00%")

header_row(ws, 9, ["Statistic", "Value", "How it's calculated"])
rows = [
    ("Relative lift", "=C7/B7-1", "+0.0%;-0.0%", "(treatment rate / control rate) - 1"),
    ("Standard error", "=SQRT(B7*(1-B7)/B5+C7*(1-C7)/C5)", "0.00000", "uncertainty of the difference"),
    ("z-score", "=(C7-B7)/B11", "0.00", "difference / standard error"),
    ("p-value", "=2*(1-NORMSDIST(ABS(B12)))", PFMT, "chance of a difference this big if there were no real effect"),
    ("95% CI low (relative)", "=(C7-B7-1.96*B11)/B7", "+0.0%;-0.0%", "lowest plausible lift"),
    ("95% CI high (relative)", "=(C7-B7+1.96*B11)/B7", "+0.0%;-0.0%", "highest plausible lift"),
    ("Significant at 5%?", '=IF(B13<0.05,"YES","NO")', None, "p-value below 0.05"),
    ("Split check p-value", "=CHIDIST(((B5-(B5+C5)/2)^2+(C5-(B5+C5)/2)^2)/((B5+C5)/2),1)", "0.000",
     "should be > 0.001, otherwise the 50/50 split broke"),
]
for i, (label, formula, fmt, how) in enumerate(rows, start=10):
    write(ws, f"A{i}", label, BOLD if label in ("Relative lift", "p-value", "Significant at 5%?") else NORMAL)
    write(ws, f"B{i}", formula, BOLD if label in ("Relative lift", "Significant at 5%?") else NORMAL, fmt)
    write(ws, f"C{i}", how, NOTE)
ws.column_dimensions["A"].width = 24
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 58

# ---- Tab 2: By device ----
ws = wb.create_sheet("By_Device")
write(ws, "A1", "Lift by device", Font(name="Arial", bold=True, size=14))
write(ws, "A2", "3 devices tested, so the significance cutoff is 0.05 / 3 (Bonferroni).", NOTE)
header_row(ws, 4, ["Device", "Control users", "Control contacted", "Treatment users", "Treatment contacted",
                   "Control rate", "Treatment rate", "Relative lift", "p-value", "Significant?"])
piv = device.pivot(index="device", columns="variant", values=["users", "contacted"])
piv = piv.loc[piv[("users", "control")].sort_values(ascending=False).index]
for r, (dev, row) in enumerate(piv.iterrows(), start=5):
    write(ws, f"A{r}", dev.capitalize(), BOLD)
    for col, key in (("B", ("users", "control")), ("C", ("contacted", "control")),
                     ("D", ("users", "treatment")), ("E", ("contacted", "treatment"))):
        write(ws, f"{col}{r}", int(row[key]), BLUE, "#,##0", INPUT_FILL)
    write(ws, f"F{r}", f"=C{r}/B{r}", fmt="0.00%")
    write(ws, f"G{r}", f"=E{r}/D{r}", fmt="0.00%")
    write(ws, f"H{r}", f"=G{r}/F{r}-1", BOLD, "+0.0%;-0.0%")
    write(ws, f"I{r}", f"=2*(1-NORMSDIST(ABS((G{r}-F{r})/SQRT(F{r}*(1-F{r})/B{r}+G{r}*(1-G{r})/D{r}))))",
          fmt=PFMT)
    write(ws, f"J{r}", f'=IF(I{r}<0.05/COUNTA($A$5:$A$7),"YES","NO")', BOLD)
for col, w in zip("ABCDEFGHIJ", [10, 14, 17, 16, 19, 13, 15, 14, 10, 12]):
    ws.column_dimensions[col].width = w

# ---- Tab 3: Sample size calculator ----
ws = wb.create_sheet("Sample_Size")
write(ws, "A1", "How many users does a test need?", Font(name="Arial", bold=True, size=14))
write(ws, "A2", "Change the yellow cells.", NOTE)
inputs = [("Baseline contact rate", 0.10, "0.0%"),
          ("Smallest lift worth detecting (relative)", 0.05, "0.0%"),
          ("Significance level", 0.05, "0.00"),
          ("Power (chance of catching a real effect)", 0.80, "0%"),
          ("Visitors per day (both groups)", 5000, "#,##0")]
for i, (label, v, fmt) in enumerate(inputs, start=4):
    write(ws, f"A{i}", label)
    write(ws, f"B{i}", v, BLUE, fmt, INPUT_FILL)
write(ws, "A10", "New rate if the lift is real")
write(ws, "B10", "=B4*(1+B5)", fmt="0.00%")
write(ws, "A11", "Users needed per group", BOLD)
write(ws, "B11", "=ROUNDUP((NORMSINV(1-B6/2)+NORMSINV(B7))^2*(B4*(1-B4)+B10*(1-B10))/(B10-B4)^2,0)",
      BOLD, "#,##0")
write(ws, "A12", "Days to run the test", BOLD)
write(ws, "B12", "=ROUNDUP(2*B11/B8,0)", BOLD, "#,##0")
write(ws, "A14", "Tip: halving the lift you want to detect needs about 4x as many users.", NOTE)
ws.column_dimensions["A"].width = 42
ws.column_dimensions["B"].width = 14

for s in wb.worksheets:
    s.sheet_view.showGridLines = False
wb.save("ab_test_results.xlsx")
print("Saved ab_test_results.xlsx")
