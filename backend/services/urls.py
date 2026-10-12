from django.urls import path

from .pdf_views import export_policy_report_pdf
from .report_views import get_loan_report, list_reports

urlpatterns = [
    path("", list_reports, name="loan-report-list"),
    path("export-pdf/", export_policy_report_pdf, name="export-policy-report-pdf"),
    path("<int:loan_request_id>/", get_loan_report, name="loan-report-detail"),
]
