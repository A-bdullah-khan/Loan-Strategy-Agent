"""Pure DB-driven PDF export for a loan request's bank comparison report.

`export_policy_report_pdf` reads only `users.models.LoanRequest` and
`banks.models.LoanPolicy` rows from PostgreSQL/SQLite and re-uses the
existing non-LLM `PredictiveBankAgent` scorer (see
`services.financial_calculator`) to rank candidate banks. No Groq/LangGraph
call is made anywhere on this path, so exporting a report never spends a
token.
"""

from datetime import UTC, datetime
from functools import partial
from io import BytesIO
from xml.sax.saxutils import escape

from django.http import FileResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from users.models import LoanRequest

from services.financial_calculator import PredictiveBankAgent

from .report_data import (
    can_access_loan_request,
    display_loan_type,
    policies_for_loan_request,
)


class ExportPolicyReportQuerySerializer(serializers.Serializer):
    loan_request_id = serializers.IntegerField(min_value=1)


# Page geometry: A4 with a uniform margin, which leaves an 18 cm wide frame
# (21 cm - 2 * 1.5 cm) that the column widths below add up to.
PAGE_MARGIN = 1.5 * cm
INPUTS_TABLE_COL_WIDTHS = [6 * cm, 12 * cm]
POLICY_TABLE_COL_WIDTHS = [5.5 * cm, 2.5 * cm, 3.25 * cm, 2.5 * cm, 4.25 * cm]
POLICY_TABLE_HEADERS = [
    "Bank Name",
    "Profit Rate",
    "Min Income",
    "Max DTI",
    "Est. Monthly Installment",
]

# A policy table up to this many rows is kept on one page with its heading.
# A longer one is left free to split across pages: forcing it together would
# push the whole table to a fresh page and leave a large gap above it.
POLICY_TABLE_KEEP_TOGETHER_MAX_ROWS = 15
# Room a long policy table needs to start on the current page: its heading,
# the header row and a few policies. With less left, it starts on a new page.
POLICY_SECTION_MIN_START_HEIGHT = 5 * cm

TABLE_HEADER_BACKGROUND = colors.HexColor("#1E293B")
TABLE_ALTERNATE_ROW_BACKGROUND = colors.HexColor("#F8FAFC")
TABLE_BORDER_COLOR = colors.HexColor("#E2E8F0")
TABLE_BORDER_WIDTH = 0.5

REPORT_TITLE = "Loan Comparison & Financial Strategy Report"

# Running header/footer, drawn by `NumberedCanvas` inside the page margin —
# i.e. outside the frame the flowables occupy, so the two never collide.
PAGE_WIDTH, PAGE_HEIGHT = A4
PAGE_CHROME_FONT_NAME = "Helvetica"
PAGE_CHROME_FONT_SIZE = 8
PAGE_CHROME_TEXT_COLOR = colors.HexColor("#64748B")
HEADER_TEXT_Y = PAGE_HEIGHT - 0.9 * cm
HEADER_LINE_Y = PAGE_HEIGHT - 1.1 * cm
FOOTER_LINE_Y = 1.1 * cm
FOOTER_TEXT_Y = 0.7 * cm

# Shared by both tables. Alignment, font and text colour are deliberately
# absent: every cell is a Paragraph, which takes those from its own
# ParagraphStyle (see `_build_styles`) and ignores the table's.
BASE_TABLE_STYLE_COMMANDS = [
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("GRID", (0, 0), (-1, -1), TABLE_BORDER_WIDTH, TABLE_BORDER_COLOR),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
]


class NumberedCanvas(Canvas):
    """A canvas that draws the report's running header and footer, including
    a "Page X of Y" count.

    The total page count isn't known until the whole document has been laid
    out, so pages are rendered in two passes: `showPage` records each
    finished page's state instead of emitting it, and `save` replays every
    recorded page — now knowing the total — adding the header/footer before
    it is actually written out.
    """

    def __init__(self, *args, generated_at: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._generated_at = generated_at
        self._saved_page_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for page_state in self._saved_page_states:
            self.__dict__.update(page_state)
            self._draw_page_chrome(total_pages)
            super().showPage()
        super().save()

    def _draw_page_chrome(self, total_pages: int) -> None:
        self.saveState()
        self.setFont(PAGE_CHROME_FONT_NAME, PAGE_CHROME_FONT_SIZE)
        self.setFillColor(PAGE_CHROME_TEXT_COLOR)
        self.setStrokeColor(TABLE_BORDER_COLOR)
        self.setLineWidth(TABLE_BORDER_WIDTH)
        # Page 1 already opens with the full-size title.
        if self._pageNumber > 1:
            self._draw_header()
        self._draw_footer(total_pages)
        self.restoreState()

    def _draw_header(self) -> None:
        self.drawString(PAGE_MARGIN, HEADER_TEXT_Y, REPORT_TITLE)
        self.line(PAGE_MARGIN, HEADER_LINE_Y, PAGE_WIDTH - PAGE_MARGIN, HEADER_LINE_Y)

    def _draw_footer(self, total_pages: int) -> None:
        self.line(PAGE_MARGIN, FOOTER_LINE_Y, PAGE_WIDTH - PAGE_MARGIN, FOOTER_LINE_Y)
        self.drawString(PAGE_MARGIN, FOOTER_TEXT_Y, f"Generated: {self._generated_at}")
        self.drawRightString(
            PAGE_WIDTH - PAGE_MARGIN,
            FOOTER_TEXT_Y,
            f"Page {self._pageNumber} of {total_pages}",
        )


def _build_styles() -> dict[str, ParagraphStyle]:
    """The report's paragraph styles, keyed by role.

    Every style sets `leading` (line height) together with `fontSize` — a
    style that only overrides `fontSize` keeps its parent's leading, and
    wrapped lines overlap once the font outgrows it — plus explicit
    `spaceBefore`/`spaceAfter`, so vertical rhythm never depends on
    ReportLab's sample-stylesheet defaults.
    """
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=18,
            leading=22,
            spaceBefore=0,
            spaceAfter=4,
        ),
        "timestamp": ParagraphStyle(
            "Timestamp",
            parent=base["Normal"],
            textColor=colors.grey,
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=16,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            fontSize=13,
            leading=17,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            spaceBefore=0,
            spaceAfter=6,
        ),
        "cell": ParagraphStyle(
            "Cell",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "cell_center": ParagraphStyle(
            "CellCenter",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "cell_label": ParagraphStyle(
            "CellLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "cell_header": ParagraphStyle(
            "CellHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            textColor=colors.white,
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "cell_header_center": ParagraphStyle(
            "CellHeaderCenter",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            fontSize=9,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
        ),
    }


def _cell(text: str, style: ParagraphStyle) -> Paragraph:
    """One table cell as a Paragraph, so long text wraps inside its column
    instead of overflowing into the next one.

    `text` is escaped first: Paragraph parses its input as markup, and a bank
    name like "A & B" would otherwise be read as a malformed entity.
    """
    return Paragraph(escape(text), style)


def _build_inputs_table(
    loan_request: LoanRequest, styles: dict[str, ParagraphStyle]
) -> Table:
    """The label/value table summarising what the user asked for."""
    banking_preference = (
        "Islamic (Shariah-compliant)"
        if loan_request.is_islamic
        else "Conventional / No preference"
    )
    rows = [
        ("Requested Amount (PKR)", f"{loan_request.required_amount:,.0f}"),
        ("Monthly Income (PKR)", f"{loan_request.monthly_income:,.0f}"),
        ("Max Tenure (Years)", str(loan_request.desired_tenure_years)),
        ("Preferred Banking", banking_preference),
    ]
    return Table(
        [
            [_cell(label, styles["cell_label"]), _cell(value, styles["cell"])]
            for label, value in rows
        ],
        colWidths=INPUTS_TABLE_COL_WIDTHS,
        style=TableStyle(
            [
                *BASE_TABLE_STYLE_COMMANDS,
                ("BACKGROUND", (0, 0), (0, -1), TABLE_ALTERNATE_ROW_BACKGROUND),
            ]
        ),
    )


def _build_policy_table(
    ranked_policies: list[dict], styles: dict[str, ParagraphStyle]
) -> Table:
    """The bank comparison table: one header row, then one row per policy.

    The bank name column is left-aligned and the numeric columns centred.
    The header row repeats at the top of every page the table spills onto.
    """
    header_row = [
        _cell(
            header, styles["cell_header" if column == 0 else "cell_header_center"]
        )
        for column, header in enumerate(POLICY_TABLE_HEADERS)
    ]
    policy_rows = [
        [
            _cell(str(policy["bank_name"]), styles["cell"]),
            _cell(f"{policy['profit_rate']:.2f}%", styles["cell_center"]),
            _cell(f"PKR {policy['min_income']:,.0f}", styles["cell_center"]),
            _cell(f"{policy['max_dti_percentage']:.1f}%", styles["cell_center"]),
            _cell(f"PKR {policy['estimated_emi']:,.0f}", styles["cell_center"]),
        ]
        for policy in ranked_policies
    ]
    return Table(
        [header_row, *policy_rows],
        colWidths=POLICY_TABLE_COL_WIDTHS,
        repeatRows=1,
        style=TableStyle(
            [
                *BASE_TABLE_STYLE_COMMANDS,
                ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BACKGROUND),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, TABLE_ALTERNATE_ROW_BACKGROUND],
                ),
            ]
        ),
    )


def _build_policy_section(
    ranked_policies: list[dict], styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    """The "Matched Bank Policies" heading with its table, or with a
    one-line notice when nothing in the catalog matched.

    The heading is never stranded at the foot of a page: a short section is
    kept whole, and a long table only starts where there is room for its
    first few rows (see POLICY_TABLE_KEEP_TOGETHER_MAX_ROWS).
    """
    heading = Paragraph("Matched Bank Policies", styles["section"])
    if not ranked_policies:
        notice = Paragraph(
            "No bank policies in the current catalog match this request.",
            styles["body"],
        )
        return [KeepTogether([heading, notice])]

    table = _build_policy_table(ranked_policies, styles)
    if len(ranked_policies) <= POLICY_TABLE_KEEP_TOGETHER_MAX_ROWS:
        return [KeepTogether([heading, table])]
    return [CondPageBreak(POLICY_SECTION_MIN_START_HEIGHT), heading, table]


def _build_pdf(loan_request: LoanRequest, ranked_policies: list[dict]) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
    )
    styles = _build_styles()
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    elements = [
        Paragraph(escape(REPORT_TITLE), styles["title"]),
        Paragraph(f"Generated: {generated_at}", styles["timestamp"]),
        KeepTogether(
            [
                Paragraph("User Inputs", styles["section"]),
                _build_inputs_table(loan_request, styles),
            ]
        ),
        *_build_policy_section(ranked_policies, styles),
    ]

    doc.build(elements, canvasmaker=partial(NumberedCanvas, generated_at=generated_at))
    buffer.seek(0)
    return buffer


@api_view(["GET"])
@permission_classes([AllowAny])
def export_policy_report_pdf(request):
    """GET /api/reports/export-pdf/?loan_request_id=<id>

    Pure DB-to-PDF renderer: fetches the LoanRequest and matching
    LoanPolicy rows already sitting in Postgres/SQLite, ranks them with the
    existing non-LLM PredictiveBankAgent, and streams a PDF back. No
    LLM/Groq call is made anywhere in this view.
    """
    query = ExportPolicyReportQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    loan_request_id = query.validated_data["loan_request_id"]

    try:
        loan_request = LoanRequest.objects.get(id=loan_request_id)
    except LoanRequest.DoesNotExist:
        return Response(
            {"detail": "Loan request not found."}, status=status.HTTP_404_NOT_FOUND
        )

    # Scoped like ChatSessionAPIView: an authenticated caller may only pull
    # a report for their own loan request. Guest (user-less) requests stay
    # open, matching how guest chat sessions work elsewhere in this API.
    if not can_access_loan_request(loan_request, request):
        return Response(
            {"detail": "Loan request not found."}, status=status.HTTP_404_NOT_FOUND
        )

    policies = policies_for_loan_request(loan_request)
    ranked_policies = PredictiveBankAgent().evaluate_and_rank(
        policies,
        {
            "monthly_income": float(loan_request.monthly_income),
            "required_amount": float(loan_request.required_amount),
            "tenure_years": loan_request.desired_tenure_years,
            "is_islamic": loan_request.is_islamic,
            "loan_type": display_loan_type(loan_request),
        },
    )

    buffer = _build_pdf(loan_request, ranked_policies)
    filename = f"loan-policy-report-{loan_request_id}.pdf"
    return FileResponse(
        buffer, as_attachment=True, filename=filename, content_type="application/pdf"
    )
