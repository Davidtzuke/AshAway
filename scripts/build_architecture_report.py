"""Build the one-page Task 6 architecture report. Needs `pip install reportlab`.

Test counts are typed in from the pytest run, so update them if the tests change.
"""
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = "docs/AshAway_Task6_Architecture_Report_Group9.pdf"
INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#52606d")
HEAD = colors.HexColor("#e6ebf0")
RULE = colors.HexColor("#b8c2cc")
ACCENT = colors.HexColor("#c2410c")

body = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=11.2, textColor=INK)
cell = ParagraphStyle("cell", parent=body, fontSize=7.9, leading=9.4)
title = ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=15)
sub = ParagraphStyle("sub", parent=body, fontSize=8, leading=9.8, textColor=MUTED)
h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=10, leading=12, spaceBefore=5, spaceAfter=2.5)


def diagram() -> Drawing:
    """Client -> interface -> orchestrator -> AI server, with storage and feeds."""
    w, h = 18.4 * cm, 2.75 * cm
    d = Drawing(w, h)
    boxes = [
        (0.0, "Traveller", "browser or JSON client", colors.white),
        (4.3, "Interface  :8000", "checks, stores, web page", HEAD),
        (9.1, "Orchestrator  :8001", "feeds, evidence, alternatives", HEAD),
        (13.9, "AI server  :8002", "the model, nothing else", HEAD),
    ]
    bw, bh, y = 3.6 * cm, 1.15 * cm, 1.3 * cm
    for x, name, note, fill in boxes:
        d.add(Rect(x * cm, y, bw, bh, rx=3, ry=3, fillColor=fill, strokeColor=RULE, strokeWidth=0.8))
        d.add(String(x * cm + bw / 2, y + 0.68 * cm, name, fontName="Helvetica-Bold", fontSize=8.6, fillColor=INK, textAnchor="middle"))
        d.add(String(x * cm + bw / 2, y + 0.28 * cm, note, fontName="Helvetica", fontSize=7, fillColor=MUTED, textAnchor="middle"))
    for (x1, *_), (x2, *_) in zip(boxes, boxes[1:]):
        a, b = x1 * cm + bw + 2, x2 * cm - 2
        for yy, label in ((y + 0.78 * cm, "request"), (y + 0.37 * cm, "answer")):
            d.add(Line(a, yy, b, yy, strokeColor=ACCENT if label == "request" else MUTED, strokeWidth=1))
            tip = b if label == "request" else a
            sign = -1 if label == "request" else 1
            d.add(Polygon([tip, yy, tip + sign * 4, yy + 2.2, tip + sign * 4, yy - 2.2],
                          fillColor=ACCENT if label == "request" else MUTED, strokeColor=None))
    for x, label in ((4.3, "SQLite file"), (9.1, "Open-Meteo, NASA FIRMS")):
        d.add(Line(x * cm + bw / 2, y - 2, x * cm + bw / 2, 0.5 * cm, strokeColor=RULE, strokeWidth=0.8))
        d.add(String(x * cm + bw / 2, 0.15 * cm, label, fontName="Helvetica", fontSize=7, fillColor=MUTED, textAnchor="middle"))
    d.add(Line(13.9 * cm, 0.55 * cm, 14.5 * cm, 0.55 * cm, strokeColor=ACCENT, strokeWidth=1))
    d.add(String(14.65 * cm, 0.47 * cm, "request (HTTP)", fontName="Helvetica", fontSize=7, fillColor=MUTED))
    d.add(Line(13.9 * cm, 0.2 * cm, 14.5 * cm, 0.2 * cm, strokeColor=MUTED, strokeWidth=1))
    d.add(String(14.65 * cm, 0.12 * cm, "answer (HTTP)", fontName="Helvetica", fontSize=7, fillColor=MUTED))
    return d


def table(header, rows, widths):
    data = [[Paragraph(f"<b>{h}</b>", cell) for h in header]] + [[Paragraph(str(v), cell) for v in r] for r in rows]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
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


SERVERS = [
    ("Interface", "8000", "Web page and JSON API. Checks every request (place, dates, May-October, 14-day horizon) before anything else runs. "
     "Forwards valid ones to the orchestrator. Stores each request, its outcome and any feedback in SQLite, with nothing about the traveller.",
     "Call the AI server. It has no address for it and imports no model code, XGBoost or pandas (tested)."),
    ("Orchestrator", "8001", "Runs the Task 5 assessment logic unchanged: weather, fire and air feeds, features, evidence checks, alternatives, comparisons. "
     "Sends every prediction to the AI server through <i>RemoteModel</i>, which has the same methods as the local model.",
     "Load the model."),
    ("AI server", "8002", "The only process that loads the model (models/live-v1). <i>/model</i> gives version, features and risk cut-offs; "
     "<i>/predict</i> gives calibrated probabilities and, on request, feature contributions. Refuses incomplete rows by name.",
     "Know about places, dates or feeds."),
]
TESTS = [
    ("U9", "Unit", "RemoteModel with an in-memory fake AI server", "Sends only the model's features, in order; reads probabilities; raises ModelUnavailable when unreachable or on HTTP 500", "4/4"),
    ("I7", "Integration", "AI server API with the real model", "Same probabilities over HTTP as in-process; missing feature refused by name", "8/8"),
    ("I8", "Integration", "Orchestrator + AI server", "Same assessment as Task 5; bad place refused before the AI server is contacted; AI down gives 503", "6/6"),
    ("I9", "Integration", "Interface + storage", "Checks, forwards and stores; bad requests never forwarded; outages passed on as 503; feedback stored", "13/13"),
    ("I10", "Integration", "All three servers on real sockets", "One request id end to end; identical answer to Task 5; stored; outages and feed failures reach the traveller", "6/6"),
]

story = [
    Paragraph("AshAway - Task 6: Distributed Architecture (preliminary report)", title),
    Paragraph("Software Engineering for CSAI 2026-2027 | Group 9 | Hammza Abas, Amin El Amrani, Rayan Fikri, Calvin Kakembo, Mikail Kaya, "
              "David Vasilescu | github.com/Davidtzuke/AshAway | code: src/ashaway/services/ | details: docs/architecture.md", sub),
    Paragraph("What we built", h2),
    Paragraph("AshAway now runs as three logical servers, each its own process and port, that talk only over HTTP. A traveller's request always "
              "goes interface &rarr; orchestrator &rarr; AI server and back. They run on one machine for now; each can move to another machine by changing one URL.", body),
    Spacer(1, 3),
    diagram(),
    table(["Server", "Port", "Does", "Never does"], SERVERS, [2.0, 1.0, 10.4, 5.0]),
    Paragraph("How the servers talk, and why HTTP", h2),
    Paragraph("Synchronous HTTP with JSON (FastAPI and uvicorn on the servers, httpx between them). A traveller waits for every answer, an assessment "
              "takes well under a second, and there are three services, so a message broker such as RabbitMQ would add a fourth process without changing "
              "what the traveller sees. If background jobs are ever needed, a queue goes into the orchestrator only. Each request gets an id that every "
              "server logs and returns (X-Request-ID), so one request can be followed through all three logs. All errors share one shape: "
              "<i>{error: {code, message, service}}</i>.", body),
    Paragraph("<b>Failures.</b> A bad request stops at the interface (400). An orchestrator or AI outage reaches the traveller as a 503 with no risk "
              "level. A failed feed is handled as in Task 5: the source is marked unavailable and 'insufficient evidence' replaces a low result. "
              "Every outcome is stored.", body),
    Paragraph("How to run it", h2),
    Paragraph("<font face='Courier'>python -m ashaway.services</font> starts all three processes; open http://127.0.0.1:8000. "
              "<font face='Courier'>--replay</font> uses recorded 2023 weather, so a demo works without internet. Or start "
              "<font face='Courier'>ashaway-ai</font>, <font face='Courier'>ashaway-orchestrator</font> and <font face='Courier'>ashaway-interface</font> "
              "in three terminals.", body),
    Paragraph("Verification", h2),
    table(["ID", "Level", "Components", "Checks", "Passed"], TESTS, [0.8, 1.7, 4.2, 10.4, 1.3]),
    Spacer(1, 2),
    Paragraph("All <b>155 tests pass</b> (87 unit, 68 integration), including the 118 from Task 5, which run unchanged against the same logic. "
              "We also started the three servers as separate processes and sent Rhodes, 18-24 July 2023, through the web page: the answer was "
              "HIGH, it made 13 calls to the AI server in about 0.26 s, and the same request id appeared in all three logs.", body),
    Paragraph("Still preliminary", h2),
    Paragraph("The servers trust each other: across a network they would need HTTPS and a shared key. SQLite suits one interface server. "
              "Requests are synchronous, and with live feeds an assessment with alternatives takes a few seconds. Not yet done: running the "
              "servers on separate machines or in the cloud, a FIRMS key for live fire detections (T12), and the full web design (T14).", body),
]

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=1.3 * cm, rightMargin=1.3 * cm, topMargin=1.1 * cm, bottomMargin=1.0 * cm,
                        title="AshAway Task 6 Architecture Report", author="Group 9")
doc.build(story)
print("wrote", OUT)
