"""Build the one-page Task 5 report. Needs `pip install reportlab`.

Result counts are typed in from the pytest run, so update them if the tests change.
"""
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = "docs/AshAway_Task5_Test_Report_Group9.pdf"
INK = colors.HexColor("#1f2933")
HEAD = colors.HexColor("#e6ebf0")
RULE = colors.HexColor("#b8c2cc")

body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.2, leading=11.4, textColor=INK, alignment=TA_LEFT)
cell = ParagraphStyle("cell", parent=body, fontSize=7.8, leading=9.1)
title = ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=15)
sub = ParagraphStyle("sub", parent=body, fontSize=8, leading=9.8, textColor=colors.HexColor("#52606d"))
h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=10, leading=12, spaceBefore=6, spaceAfter=2.5)

UNIT = [
    ("U1", "validate_request", "'atlantis'; end before start; 31 Oct to 1 Nov; end 15 days ahead. Also Rhodes, 2-4 July, today 1 July.",
     "Rejected with unsupported_place; reversed_dates; out_of_season; beyond_horizon. Accepted with 3 days.",
     "Guessing outside our scope would give false advice (FR1, FR9).", "14/14"),
    ("U2", "risk_level, cut-offs 0.2 and 0.5", "0.199; 0.2; 0.499; 0.5; also 1.01 and NaN.", "low; medium; medium; high; ValueError.",
     "Off-by-one errors live at boundaries (FR2).", "10/10"),
    ("U3", "is_stale, check_evidence", "Value 2 days old; 3 days old; none. Low forecast with 3 fires nearby.", "Current; stale; stale. Conflict flagged.",
     "Old data must never look reassuring (FR5).", "11/11"),
    ("U4", "parse_weather", "30 C, 40%, 5 mm. Rain null. {\"error\": true}.", "303.15 K, 0.40, 0.005 m. NaN, not 0. ValueError.",
     "Wrong units or an invented 0 silently corrupt a score (NFR5).", "5/5"),
    ("U5", "window_features, daily_feature_rows", "8 days with 2 mm rain 2 days ago. Weather including the day itself. Gap in history.",
     "rain_7d 0.0025, days_since_rain 2. Uses only the day before. No row.", "Inputs must match training and not see the future (NFR9).", "6/6"),
    ("U6", "lower_risk_alternatives", "High risk; candidates at high, medium, low, and low with poor coverage.", "Low, then medium. Others excluded.",
     "An equal-risk 'alternative' would mislead (FR6, AI6).", "3/3"),
    ("U7", "choose_threshold_f2, fit_calibration, high_threshold", "Toy labels and scores with a known answer.",
     "Threshold 0.4; monotonic calibration; lowest score reaching the precision target.", "Cut-offs decide what travellers see (NFR9, AI5).", "3/3"),
    ("U8", "in_greece", "Athens, Rhodes, Corfu. Izmir, Tirana, open sea.", "True. False.", "Greek results must not include neighbours (AI4).", "6/6"),
]
INTEGRATION = [
    ("I1", "Loader + split + data report", "114 real Track A samples.",
     "Inputs stop the day before the label; no outcome columns; 36 per split at 2:1; report shows 114 raw, 6 removed, 108 clean.",
     "Guards the fire-day leak we found in the first loader (AI2, NFR2, NFR9).", "4/4"),
    ("I2", "Training + calibration + save + load", "Same sample.", "Reloaded model gives identical predictions; record lists 5 models and all NFR8 metrics.",
     "Each prediction must be reproducible (NFR4, NFR8).", "5/5"),
    ("I3", "Feeds + features + model + service", "Rhodes, 18-24 July 2023, recorded feeds. Chania, 1-3 June 2023, with no fires, then 1 fire nearby.",
     "High, 7 days, every item labelled, dated and sourced, nothing after 17 July. Low. Insufficient evidence with a conflict warning.",
     "A known real event checks the whole answer (FR2-4, FR8).", "6/6"),
    ("I4", "Feeds + service, under failure", "Weather HTTP 500. Fire feed down with a low, then a high forecast. Air quality down.",
     "No score or reasons, source unavailable. Insufficient evidence; high stays with a warning. No air item.",
     "Failure must never read as 'safe' (FR5, NFR5).", "8/8"),
    ("I5", "Service across destinations", "Rhodes, 1-3 July 2023. Rhodes and Chania on the same dates.",
     "1-3 alternatives, strictly lower and sorted. One comparable row per place.", "Advice must compare like with like (FR6, FR7).", "4/4"),
    ("I6", "Command line + service + feeds", "assess rhodes 2023-07-18 2023-07-24. assess atlantis ...; December dates.",
     "Exit 0, risk in words, reasons, labels, disclaimer. Exit 2, reason, no risk level.", "This is what a traveller really sees (UR1-4, NFR6).", "8/8"),
]


def table(rows, first_col):
    header = ["ID", first_col, "Test input", "Expected output (all matched)", "Why this test", "Passed"]
    data = [[Paragraph(f"<b>{h}</b>", cell) for h in header]]
    data += [[Paragraph(str(v), cell) for v in row] for row in rows]
    t = Table(data, colWidths=[0.65 * cm, 3.45 * cm, 4.1 * cm, 4.7 * cm, 4.2 * cm, 1.3 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]))
    return t


story = [
    Paragraph("AshAway - Task 5: Testing Report", title),
    Paragraph("Software Engineering for CSAI 2026-2027 | Group 9 | Client: WanderGuard | Hammza Abas, Amin El Amrani, Rayan Fikri, "
              "Calvin Kakembo, Mikail Kaya, David Vasilescu | github.com/Davidtzuke/AshAway", sub),
    Paragraph("Approach and why these tests", h2),
    Paragraph("AshAway's worst failure is false reassurance: a traveller told nothing is wrong when we simply don't know. We chose tests around the ways "
              "that could happen: bad requests, wrong units, future data leaking into the model, and failing feeds. Unit tests check one function with "
              "hand-computed answers. Integration tests check that components work together, using real data. <b>pytest</b> runs them all automatically, and "
              "<b>GitHub Actions</b> runs them on every push.", body),
    Paragraph("Unit tests: one function, no files or network", h2),
    table(UNIT, "Unit"),
    Paragraph("Integration tests: several components together", h2),
    table(INTEGRATION, "Components"),
    Paragraph("Test data", h2),
    Paragraph("<b>Hand-computed values</b> for unit tests. <b>A real Mesogeos Track A sample</b>: 114 samples, 3,420 rows, with real gaps and fire days, small enough "
              "for automated runs. <b>Recorded Open-Meteo responses</b> from 2023, including the July Rhodes heatwave. <b>Simulated HTTP 500 errors</b>, since real "
              "services don't fail on demand. <b>Hand-written FIRMS files</b> in NASA's documented format, which are not real detections, because our API key "
              "isn't set up yet.", body),
    Paragraph("Results", h2),
    Paragraph("<b>All 118 tests pass</b> (83 unit, 35 integration), locally and on GitHub Actions, in about 5 seconds, with 93% line coverage. The table counts the 93 tests "
              "tied to a case; 25 more unit tests cover smaller helpers. To check that the tests can fail, we broke the code on purpose in 8 ways, such as feeding "
              "the fire day to the model or treating missing rain as zero, and <b>all 8 were caught</b>.", body),
    Paragraph("<b>What this does not show.</b> Passing tests mean the software behaves as specified, not that the forecast is accurate. On real data the model reaches recall 0.949 "
              "(Mediterranean test years) and 0.936 (Greece, May-October), but in Greece its AUPRC is below a simple baseline (0.595 vs 0.698, on 47 fires), so SRS criterion "
              "AI3(b) is not yet met there. The live FIRMS service and live forecast weather are untested, and the user-acceptance targets still need real users.", body),
    Spacer(1, 1),
]

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=1.3 * cm, rightMargin=1.3 * cm, topMargin=1.1 * cm, bottomMargin=1.0 * cm,
                        title="AshAway Task 5 Testing Report", author="Group 9")
doc.build(story)
print("wrote", OUT)
