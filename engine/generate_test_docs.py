#!/usr/bin/env python3
"""T4 — Generate ~22 fake test documents in inbox/.

Creates a realistic mix of PDFs and DOCXs: some with clear names, some
with useless scan/doc filenames (content reveals identity), one lender
draft/redline (should route to Drafts, untracked), and one decoy file
(should end up in NEEDS_REVIEW).

Intentionally leaves gaps for the missing report:
  - No Surveys (all 4 assets)
  - No Insurance Certificates (all 4 assets)
  - Missing Guarantor Financials for Meridian REF III GP, LLC
  - No Fund LPA, GP Formation Documents, or Sponsor Guaranty
  - No executed Loan Agreement (only a draft), no Assignment of Leases
    and Rents, no Interest Rate Cap Agreement, no Legal Opinion
  - Rent roll / operating statement for only 1 asset each
"""

import os
import zipfile
from io import BytesIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "inbox")

# ── PDF writer (standard library only, no dependencies) ──────────────


def _escape_pdf(text):
    # Replace non-latin-1 characters with ASCII equivalents
    text = text.replace("\u2014", "--").replace("\u2013", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text, width=78):
    lines = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        words = para.split()
        buf, length = [], 0
        for w in words:
            if length + len(w) + (1 if buf else 0) > width:
                lines.append(" ".join(buf))
                buf, length = [w], len(w)
            else:
                buf.append(w)
                length += len(w) + (1 if len(buf) > 1 else 0)
        if buf:
            lines.append(" ".join(buf))
    return lines


def write_pdf(path, title, body):
    """Create a minimal single-page PDF with title and body text."""
    text_lines = _wrap(body)

    # Build content stream
    parts = ["BT", "/F1 13 Tf", "1 0 0 1 72 740 Tm",
             f"({_escape_pdf(title)}) Tj", "/F1 10 Tf"]
    y = 714
    for line in text_lines:
        if y < 50:
            break
        parts.append(f"1 0 0 1 72 {y} Tm")
        parts.append(f"({_escape_pdf(line)}) Tj")
        y -= (14 if line else 8)
    parts.append("ET")
    stream = "\n".join(parts)

    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")

    xref_pos = len(out)
    xref = f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n"
    out += xref.encode("latin-1")
    out += (f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode("latin-1")

    with open(path, "wb") as f:
        f.write(out)


# ── DOCX writer (standard library: zipfile + XML) ───────────────────


def _xml_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_docx(path, title, body):
    """Create a minimal DOCX with title and body paragraphs."""
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types"><Default Extension="rels" ContentType='
          '"application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType='
          '"application/vnd.openxmlformats-officedocument.'
          'wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type='
            '"http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/'
             'package/2006/relationships"></Relationships>')

    paras = (
        '<w:p><w:pPr><w:jc w:val="center"/><w:rPr><w:b/><w:sz w:val="26"/>'
        '</w:rPr></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="26"/></w:rPr>'
        f'<w:t>{_xml_esc(title)}</w:t></w:r></w:p>'
    )
    for p in body.split("\n"):
        paras += (f'<w:p><w:r><w:t xml:space="preserve">'
                  f'{_xml_esc(p.strip())}</w:t></w:r></w:p>')

    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/'
           'wordprocessingml/2006/main"><w:body>'
           + paras + '</w:body></w:document>')

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/_rels/document.xml.rels", drels)
        zf.writestr("word/document.xml", doc)
    with open(path, "wb") as f:
        f.write(buf.getvalue())


# ── Document definitions ────────────────────────────────────────────
# (filename, title, body, format)

DOCUMENTS = [
    # ━━ 1  Organizational & KYC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (
        "Formation_Certificate_Meridian_Holdings.pdf",
        "Certificate of Formation — Limited Liability Company",
        "STATE OF DELAWARE\n"
        "DIVISION OF CORPORATIONS\n\n"
        "I, Jeffrey W. Bullock, Secretary of State of the State of "
        "Delaware, do hereby certify that MERIDIAN MULTIFAMILY HOLDINGS "
        "LLC was duly formed as a Delaware limited liability company on "
        "March 14, 2019, as evidenced by the Certificate of Formation "
        "filed in this office on said date.\n\n"
        "File Number: 7284913\n\n"
        "IN WITNESS WHEREOF, I have hereunto set my hand and official "
        "seal at the City of Dover this 14th day of March, 2019.\n\n"
        "Jeffrey W. Bullock\n"
        "Secretary of State",
        "pdf",
    ),
    (
        "scan_0042.pdf",
        "Amended and Restated Limited Partnership Agreement",
        "AMENDED AND RESTATED AGREEMENT OF LIMITED PARTNERSHIP\n"
        "OF\n"
        "MERIDIAN REAL ESTATE FUND III, L.P.\n\n"
        "This Amended and Restated Agreement of Limited Partnership of "
        "Meridian Real Estate Fund III, L.P. (the 'Partnership') is "
        "entered into as of June 1, 2018, by and among Meridian REF III "
        "GP, LLC, a Delaware limited liability company, as General "
        "Partner, and each of the limited partners identified on "
        "Schedule A hereto.\n\n"
        "ARTICLE I — ORGANIZATION\n\n"
        "1.1 Formation. The Partnership was formed as a limited "
        "partnership under the Delaware Revised Uniform Limited "
        "Partnership Act on May 15, 2018 by filing a Certificate of "
        "Limited Partnership with the Secretary of State of Delaware.\n\n"
        "1.2 Name. The name of the Partnership is Meridian Real Estate "
        "Fund III, L.P.",
        "pdf",
    ),
    (
        "Good_Standing_Meridian_GP.pdf",
        "Certificate of Good Standing",
        "STATE OF DELAWARE\n"
        "DIVISION OF CORPORATIONS\n\n"
        "I, Jeffrey W. Bullock, Secretary of State of the State of "
        "Delaware, do hereby certify that MERIDIAN REF III GP, LLC, "
        "File Number 7195528, is in good standing under the laws of the "
        "State of Delaware as of the date of this certificate.\n\n"
        "The entity was formed on January 22, 2018, and has paid all "
        "fees and taxes currently due and owing.\n\n"
        "Certificate Number: 2024-GS-041827\n"
        "Date: February 12, 2024",
        "pdf",
    ),
    (
        "W-9_Meridian_Holdings.docx",
        "Form W-9 — Request for Taxpayer Identification Number",
        "Name: Meridian Multifamily Holdings LLC\n"
        "Business name / disregarded entity name: N/A\n"
        "Federal tax classification: Limited Liability Company\n"
        "Address: 200 Park Avenue, Suite 3200, New York, NY 10166\n"
        "TIN: 84-2937105\n\n"
        "Certification: Under penalties of perjury, I certify that the "
        "number shown on this form is my correct taxpayer identification "
        "number and that I am not subject to backup withholding.",
        "docx",
    ),
    (
        "doc(3).pdf",
        "Certification Regarding Beneficial Ownership of Legal Entity Customers",
        "Legal Entity Name: Meridian Multifamily Holdings LLC\n"
        "Entity Type: Limited Liability Company\n"
        "State of Formation: Delaware\n"
        "Principal Place of Business: 200 Park Avenue, Suite 3200, "
        "New York, NY 10166\n\n"
        "The following individual(s) are the beneficial owners of 25% "
        "or more of the equity interests of the above-named entity:\n\n"
        "1. James R. Whitfield, Managing Director\n"
        "   DOB: 04/15/1972\n"
        "   Address: 14 East 75th Street, New York, NY 10021\n"
        "   SSN: XXX-XX-4218",
        "pdf",
    ),

    # ━━ 2  Third-Party Reports ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (
        "Appraisal_Oakline_Commons.pdf",
        "Appraisal Report — Oakline Commons Apartments",
        "CUSHMAN & WAKEFIELD VALUATION & ADVISORY\n\n"
        "Property: Oakline Commons\n"
        "Address: 450 Oakline Drive, Dallas, TX 75208\n"
        "Property Type: Multifamily — 312 Units\n"
        "Effective Date of Value: January 15, 2024\n"
        "Client: First Continental Bank, N.A.\n\n"
        "MARKET VALUE CONCLUSION\n"
        "As Is Market Value: $34,200,000\n\n"
        "The subject is a 312-unit garden-style apartment community "
        "constructed in 2006 and renovated in 2021, located in the "
        "Oak Cliff submarket of Dallas, Texas.",
        "pdf",
    ),
    (
        "Appraisal_Brazos_Bend.pdf",
        "Appraisal Report — Brazos Bend Apartments",
        "CUSHMAN & WAKEFIELD VALUATION & ADVISORY\n\n"
        "Property: Brazos Bend Apartments\n"
        "Address: 2200 Brazos Bend Blvd, Houston, TX 77089\n"
        "Property Type: Multifamily — 276 Units\n"
        "Effective Date of Value: January 18, 2024\n"
        "Client: First Continental Bank, N.A.\n\n"
        "MARKET VALUE CONCLUSION\n"
        "As Is Market Value: $28,750,000\n\n"
        "The subject is a 276-unit mid-rise apartment community "
        "constructed in 2009 in the Pearland/Clear Lake submarket "
        "of Houston, Texas.",
        "pdf",
    ),
    (
        "IMG_20240815.pdf",
        "Property Condition Assessment Report",
        "EMG ENGINEERING\n\n"
        "Property: Hill Country Flats\n"
        "Address: 88 Ranch Road 620, Austin, TX 78734\n"
        "Property Type: Multifamily — 198 Units\n"
        "Assessment Date: January 22, 2024\n"
        "Client: First Continental Bank, N.A.\n\n"
        "EXECUTIVE SUMMARY\n\n"
        "EMG was retained to conduct a Property Condition Assessment of "
        "Hill Country Flats, a 198-unit garden-style apartment community "
        "in the Lake Travis area of Austin, Texas. Constructed in 2012, "
        "the property is in good condition. Estimated Immediate Repair "
        "Cost: $42,500. Replacement Reserve (12-year): $1,850,000.",
        "pdf",
    ),
    (
        "Phase_I_ESA_Mission_Verde.pdf",
        "Phase I Environmental Site Assessment — Mission Verde Residences",
        "PARTNER ENGINEERING AND SCIENCE, INC.\n\n"
        "Phase I Environmental Site Assessment — ASTM E1527-21\n\n"
        "Property: Mission Verde Residences\n"
        "Address: 1500 Mission Verde Way, San Antonio, TX 78214\n"
        "Assessment Date: January 25, 2024\n"
        "Client: First Continental Bank, N.A.\n\n"
        "FINDINGS: This assessment has revealed no evidence of "
        "recognized environmental conditions (RECs) in connection with "
        "the Mission Verde Residences property in San Antonio, Texas.",
        "pdf",
    ),
    (
        "Zoning_Report_Oakline.docx",
        "Zoning Compliance Report — Oakline Commons",
        "PREPARED BY: ALT & ASSOCIATES, P.C.\n\n"
        "Property: Oakline Commons\n"
        "Address: 450 Oakline Drive, Dallas, TX 75208\n"
        "Zoning District: MF-2(A) — Multifamily\n"
        "Report Date: January 20, 2024\n\n"
        "CONCLUSION: The subject property is a legally permitted use "
        "within the MF-2(A) Multifamily district. No variances or "
        "special permits are required. Existing improvements conform to "
        "all applicable setback, height, density, and parking "
        "requirements of the City of Dallas zoning ordinance.",
        "docx",
    ),
    (
        "Title_Commitment_Brazos_Bend.pdf",
        "Commitment for Title Insurance",
        "FIDELITY NATIONAL TITLE INSURANCE COMPANY\n"
        "Commitment No.: FCB-2024-01892\n\n"
        "Property: Brazos Bend Apartments\n"
        "Address: 2200 Brazos Bend Blvd, Houston, TX 77089\n"
        "Proposed Insured: First Continental Bank, N.A.\n"
        "Amount of Insurance: $42,000,000.00\n"
        "Effective Date: February 1, 2024\n\n"
        "Fidelity National Title Insurance Company commits to issue its "
        "policy of title insurance in favor of the Proposed Insured, "
        "subject to the Requirements and Exceptions in Schedules B-I "
        "and B-II attached hereto.",
        "pdf",
    ),

    # ━━ 3  Security & Collateral ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (
        "Mortgage_Oakline_Commons.pdf",
        "Deed of Trust, Assignment of Leases and Rents, Security "
        "Agreement and Fixture Filing",
        "Recording Requested By: First Continental Bank, N.A.\n\n"
        "DEED OF TRUST\n\n"
        "Grantor: Meridian Multifamily Holdings LLC\n"
        "Trustee: Commonwealth Land Title Company\n"
        "Beneficiary: First Continental Bank, N.A.\n\n"
        "Property: Oakline Commons\n"
        "Address: 450 Oakline Drive, Dallas, TX 75208\n\n"
        "THIS DEED OF TRUST is made as of [Closing Date], 2024, by "
        "Meridian Multifamily Holdings LLC, a Delaware limited liability "
        "company (Grantor), to Commonwealth Land Title Company (Trustee),"
        " for the benefit of First Continental Bank, N.A. (Beneficiary),"
        " to secure the Indebtedness described herein.",
        "pdf",
    ),
    (
        "UCC-1_Brazos_Bend.pdf",
        "UCC Financing Statement",
        "UNIFORM COMMERCIAL CODE — FINANCING STATEMENT (UCC-1)\n\n"
        "Filing Office: Texas Secretary of State\n\n"
        "DEBTOR: Meridian Multifamily Holdings LLC\n"
        "200 Park Avenue, Suite 3200, New York, NY 10166\n\n"
        "SECURED PARTY: First Continental Bank, N.A.\n"
        "101 California Street, 42nd Floor, San Francisco, CA 94111\n\n"
        "COLLATERAL: All personal property of Debtor now owned or "
        "hereafter acquired located at or related to Brazos Bend "
        "Apartments, 2200 Brazos Bend Blvd, Houston, TX 77089, "
        "including furniture, fixtures, equipment, accounts, contract "
        "rights, and general intangibles.",
        "pdf",
    ),

    # ━━ 4  Principal Loan Documents ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (
        "Loan_Agreement_Lender_Draft_Redline_v3.docx",
        "LOAN AGREEMENT — LENDER'S DRAFT / REDLINE v3",
        "DRAFT — FOR DISCUSSION PURPOSES ONLY\n"
        "PRIVILEGED AND CONFIDENTIAL\n\n"
        "LOAN AGREEMENT\n"
        "dated as of [___], 2024\n\n"
        "among\n"
        "MERIDIAN MULTIFAMILY HOLDINGS LLC, as Borrower,\n"
        "and\n"
        "FIRST CONTINENTAL BANK, N.A., as Lender\n\n"
        "$42,000,000 Senior Secured Term Loan Facility\n\n"
        "[LENDER REDLINE — TRACKED CHANGES FROM BORROWER DRAFT]\n\n"
        "Article I. DEFINITIONS AND INTERPRETATION\n"
        "Section 1.01. Defined Terms.\n"
        "'Borrower' means Meridian Multifamily Holdings LLC, a Delaware "
        "limited liability company.",
        "docx",
    ),
    (
        "Promissory_Note.pdf",
        "Promissory Note",
        "PROMISSORY NOTE\n\n"
        "$42,000,000.00\n"
        "New York, New York\n"
        "[Closing Date], 2024\n\n"
        "FOR VALUE RECEIVED, Meridian Multifamily Holdings LLC, a "
        "Delaware limited liability company (the 'Maker'), hereby "
        "unconditionally promises to pay to the order of First "
        "Continental Bank, N.A. (the 'Payee') the principal sum of "
        "FORTY-TWO MILLION AND 00/100 DOLLARS ($42,000,000.00), together"
        " with interest thereon as set forth in the Loan Agreement dated "
        "as of [Closing Date], 2024.\n\n"
        "Interest shall accrue at Term SOFR (1-month) plus 2.65% per "
        "annum, subject to a SOFR floor of 0.25%. Interest is payable "
        "monthly in arrears.",
        "pdf",
    ),
    (
        "Guaranty.docx",
        "Guaranty of Non-Recourse Carveouts",
        "GUARANTY OF NON-RECOURSE CARVEOUTS\n\n"
        "This GUARANTY is made as of [Closing Date], 2024, by MERIDIAN "
        "REAL ESTATE FUND III, L.P., a Delaware limited partnership (the "
        "'Fund Guarantor'), and MERIDIAN REF III GP, LLC, a Delaware "
        "limited liability company (the 'GP Guarantor,' and together "
        "with the Fund Guarantor, jointly and severally, the "
        "'Guarantors'), for the benefit of FIRST CONTINENTAL BANK, N.A."
        " (the 'Lender').\n\n"
        "The Guarantors hereby absolutely, unconditionally, and "
        "irrevocably guarantee to the Lender the payment and performance"
        " of the Guaranteed Obligations as defined in Section 2 hereof.",
        "docx",
    ),
    (
        "attachment_final_v2.pdf",
        "Closing Certificate",
        "CLOSING CERTIFICATE\n\n"
        "Reference is made to that certain Loan Agreement dated as of "
        "[Closing Date], 2024 (the 'Loan Agreement'), by and between "
        "Meridian Multifamily Holdings LLC (the 'Borrower') and First "
        "Continental Bank, N.A. (the 'Lender').\n\n"
        "The undersigned, a duly authorized representative of the "
        "Borrower, hereby certifies to the Lender as follows:\n\n"
        "1. The representations and warranties of the Borrower in the "
        "Loan Agreement are true and correct in all material respects.\n"
        "2. No Default or Event of Default has occurred or is "
        "continuing.\n"
        "3. All conditions precedent to the initial advance have been "
        "satisfied.",
        "pdf",
    ),

    # ━━ 5  Due Diligence ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (
        "Rent_Roll_Oakline_Commons.pdf",
        "Certified Rent Roll — Oakline Commons",
        "CERTIFIED RENT ROLL\n"
        "As of January 31, 2024\n\n"
        "Property: Oakline Commons\n"
        "Address: 450 Oakline Drive, Dallas, TX 75208\n"
        "Total Units: 312\n"
        "Occupied Units: 298 (95.5%)\n\n"
        "Unit Mix Summary:\n"
        "  1BR/1BA (140 units): Avg Rent $1,285/mo\n"
        "  2BR/2BA (132 units): Avg Rent $1,640/mo\n"
        "  3BR/2BA  (40 units): Avg Rent $2,010/mo\n\n"
        "Total Monthly Gross Potential Rent: $463,820\n"
        "Effective Gross Rent: $439,585\n\n"
        "I hereby certify that the foregoing rent roll is true, correct, "
        "and complete.\n\n"
        "Meridian Multifamily Holdings LLC\n"
        "By: James R. Whitfield, Authorized Signatory",
        "pdf",
    ),
    (
        "Document1.docx",
        "Annual Operating Statement — Brazos Bend Apartments",
        "ANNUAL OPERATING STATEMENT\n"
        "For the Year Ended December 31, 2023\n\n"
        "Property: Brazos Bend Apartments\n"
        "Address: 2200 Brazos Bend Blvd, Houston, TX 77089\n"
        "Units: 276\n\n"
        "REVENUE\n"
        "  Gross Potential Rent:         $4,876,800\n"
        "  Less: Vacancy Loss:            ($243,840)\n"
        "  Other Income:                    $187,200\n"
        "  Effective Gross Income:        $4,820,160\n\n"
        "OPERATING EXPENSES\n"
        "  Real Estate Taxes:               $612,000\n"
        "  Insurance:                       $189,500\n"
        "  Repairs & Maintenance:           $324,000\n"
        "  Utilities:                       $276,000\n"
        "  Management Fee (3.5%):           $168,706\n"
        "  General & Administrative:         $96,000\n"
        "  Total Operating Expenses:      $1,666,206\n\n"
        "NET OPERATING INCOME:            $3,153,954",
        "docx",
    ),
    (
        "Guarantor_Financials_Fund_III.pdf",
        "Financial Statements — Meridian Real Estate Fund III, L.P.",
        "MERIDIAN REAL ESTATE FUND III, L.P.\n"
        "AUDITED FINANCIAL STATEMENTS\n"
        "For the Year Ended December 31, 2023\n"
        "(Audited by Deloitte & Touche LLP)\n\n"
        "BALANCE SHEET — December 31, 2023\n\n"
        "ASSETS\n"
        "  Real Estate Investments (net):   $412,500,000\n"
        "  Cash and Cash Equivalents:        $28,750,000\n"
        "  Other Assets:                     $14,200,000\n"
        "  Total Assets:                    $455,450,000\n\n"
        "LIABILITIES AND PARTNERS' CAPITAL\n"
        "  Mortgage Loans Payable:          $287,000,000\n"
        "  Other Liabilities:                $12,350,000\n"
        "  Partners' Capital:               $156,100,000\n"
        "  Total:                           $455,450,000",
        "pdf",
    ),

    # ━━ 6  Sponsor & Fund ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (
        "Structure_Org_Chart.pdf",
        "Organizational Structure Chart",
        "MERIDIAN MULTIFAMILY HOLDINGS LLC\n"
        "ORGANIZATIONAL STRUCTURE CHART\n\n"
        "Meridian Capital Partners (Sponsor)\n"
        "  |\n"
        "  +-- Meridian REF III GP, LLC (General Partner, DE LLC)\n"
        "  |     |\n"
        "  |     +-- Meridian Real Estate Fund III, L.P. (Fund, DE LP)\n"
        "  |           |\n"
        "  |           +-- Meridian Multifamily Holdings LLC "
        "(Borrower, DE LLC)\n"
        "  |                 |\n"
        "  |                 +-- Oakline Commons (Dallas, TX)\n"
        "  |                 +-- Brazos Bend Apartments (Houston, TX)\n"
        "  |                 +-- Hill Country Flats (Austin, TX)\n"
        "  |                 +-- Mission Verde Residences "
        "(San Antonio, TX)\n\n"
        "Guarantors: Meridian Real Estate Fund III, L.P. and Meridian "
        "REF III GP, LLC\n"
        "Lender: First Continental Bank, N.A.",
        "pdf",
    ),

    # ━━ DECOY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    (
        "TeamLunchMenu_August.pdf",
        "August Team Lunch — Menu Selection",
        "Hi everyone!\n\n"
        "Please find below the menu options for our August team lunch "
        "at Carmine's on Friday the 16th. Reply with your selection by "
        "Wednesday EOD.\n\n"
        "APPETIZERS (choose one)\n"
        "  - Caesar Salad\n"
        "  - Fried Calamari\n"
        "  - Mozzarella & Tomato\n\n"
        "ENTREES (choose one)\n"
        "  - Chicken Parmigiana\n"
        "  - Penne alla Vodka\n"
        "  - Veal Marsala\n"
        "  - Grilled Salmon\n\n"
        "DESSERT: Tiramisu (shared family-style)\n\n"
        "Thanks,\nLisa from Office Services",
        "pdf",
    ),
]


# What each file actually is (for reference / printed summary)
IDENTITIES = [
    "Formation Certificate — Meridian Multifamily Holdings LLC",
    "Operating Agreement / LPA — Meridian Real Estate Fund III, L.P.  [useless filename: scan_0042.pdf]",
    "Good Standing Certificate — Meridian REF III GP, LLC",
    "W-9 — Meridian Multifamily Holdings LLC",
    "Beneficial Ownership Certification — Meridian Multifamily Holdings LLC  [useless filename: doc(3).pdf]",
    "Appraisal — Oakline Commons",
    "Appraisal — Brazos Bend Apartments",
    "Property Condition Assessment — Hill Country Flats  [useless filename: IMG_20240815.pdf]",
    "Phase I Environmental Site Assessment — Mission Verde Residences",
    "Zoning Report — Oakline Commons",
    "Title Commitment — Brazos Bend Apartments",
    "Mortgage / Deed of Trust — Oakline Commons",
    "UCC-1 Financing Statement — Brazos Bend Apartments",
    "Loan Agreement — LENDER DRAFT REDLINE  [should route to 4.1 Drafts, untracked]",
    "Promissory Note — deal (executed)",
    "Guaranty — deal (executed)",
    "Closing Certificate — deal (executed)  [useless filename: attachment_final_v2.pdf]",
    "Rent Roll — Oakline Commons",
    "Operating Statement — Brazos Bend Apartments  [useless filename: Document1.docx]",
    "Guarantor Financial Statements — Meridian Real Estate Fund III, L.P.",
    "Structure / Org Chart — deal",
    "DECOY — lunch menu  [should route to NEEDS_REVIEW]",
]


def main():
    os.makedirs(INBOX, exist_ok=True)
    # Remove .gitkeep if present
    gitkeep = os.path.join(INBOX, ".gitkeep")
    if os.path.exists(gitkeep):
        os.remove(gitkeep)

    for i, (filename, title, body, fmt) in enumerate(DOCUMENTS):
        path = os.path.join(INBOX, filename)
        if fmt == "pdf":
            write_pdf(path, title, body)
        else:
            write_docx(path, title, body)

    print(f"Generated {len(DOCUMENTS)} files in inbox/\n")
    print(f"{'#':<4} {'Filename':<48} Identity")
    print("-" * 110)
    for i, ((filename, *_), identity) in enumerate(
            zip(DOCUMENTS, IDENTITIES), 1):
        print(f"{i:<4} {filename:<48} {identity}")

    print(f"\nMissing doc types (intentional gaps for report):")
    print("  - Surveys (all 4 assets)")
    print("  - Insurance Certificates (all 4 assets)")
    print("  - Guarantor Financials for Meridian REF III GP, LLC")
    print("  - Fund LPA, GP Formation Documents, Sponsor Guaranty")
    print("  - Executed Loan Agreement, Assignment of Leases and Rents,")
    print("    Interest Rate Cap Agreement, Legal Opinion")
    print("  - Most per-asset KYC, third-party reports, security docs,")
    print("    rent rolls, and operating statements")


if __name__ == "__main__":
    main()
