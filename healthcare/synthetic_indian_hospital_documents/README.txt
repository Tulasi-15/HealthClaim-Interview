SYNTHETIC INDIAN HOSPITAL DOCUMENTS FOR SOFTWARE TESTING
==========================================================

DISCLAIMER:
All hospital names, patient names, patient IDs, doctors, registration numbers,
addresses, dates, and financial amounts in this archive are completely FICTIONAL.
These documents are created strictly for software development, document intelligence,
PDF text extraction, and OCR testing. They are NOT real medical records.

CONTENTS OF THIS ARCHIVE:
-------------------------
1. Digital PDFs (Selectable Embedded Text):
   - 01_riverbend_discharge_summary.pdf  (Discharge Summary – Riverbend Multispeciality Hospital)
   - 02_sunrise_discharge_summary.pdf    (Discharge Summary – Sunrise Community Hospital)
   - 03_riverbend_final_bill.pdf         (Final Hospital Bill – Riverbend Multispeciality Hospital)
   - 04_greenfield_final_bill.pdf        (Final Hospital Bill – Greenfield General Hospital)
   - 05_lakeshore_itemized_bill.pdf      (Detailed Itemized Hospital Bill – Lakeshore Surgical Centre)
   - 06_citycare_pharmacy_bill.pdf       (Inpatient Pharmacy Bill – CityCare Pharmacy – Hospital Dispensary)

2. Scanned-Style PDFs (Image-Only, No Selectable Text):
   - 02_sunrise_discharge_summary_scanned.pdf
   - 04_greenfield_final_bill_scanned.pdf
   - 06_citycare_pharmacy_bill_scanned.pdf

3. Ground Truth & Documentation:
   - expected_values.csv  (Expected extracted metadata and financial values for all 9 PDFs)
   - README.txt           (This documentation file)

HOW TO USE FOR TESTING PDF TEXT EXTRACTION AND OCR:
---------------------------------------------------
1. Digital Text Detection:
   - Use PyMuPDF (fitz) or pypdf to extract text from each PDF.
   - The 6 original digital PDFs will return full selectable text directly.
   - The 3 *_scanned.pdf files contain image-only pages and will return empty text strings,
     allowing you to test your application's scanned-page detection routing.

2. OCR Pipeline Testing:
   - Route pages with empty/minimal extracted text to Tesseract OCR (e.g., pytesseract).
   - Render the scanned PDF pages at 200-300 DPI and run OCR to verify text recovery.

3. Structured Extraction & Reconciliation Validation:
   - Compare your pipeline's extracted JSON/fields against expected_values.csv.
   - Note that 03_riverbend_final_bill.pdf reports Net Bill = INR 62,000 and Balance Payable = INR 42,000
     (after INR 20,000 advance), and 04_greenfield_final_bill.pdf reports Net Bill = INR 36,000 and
     Amount Due = INR 26,000 (after INR 10,000 advance).
