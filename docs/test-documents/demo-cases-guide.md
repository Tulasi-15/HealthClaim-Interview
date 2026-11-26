# Simple synthetic demonstration cases

All documents, patients, hospitals, dates and amounts in this folder are fictional and are for software testing only. Each case has its own folder (D01, D02 or D03). Each claim must use documents with the same case number. Do not combine patients in one claim.

| Case | Diagnosis in discharge summary | ICD-10 suggestion | Procedure |
| --- | --- | --- | --- |
| D01 | Cataract | H26.9 (unspecified) | Cataract surgery |
| D02 | Carpal tunnel syndrome | G56.0 | Carpal tunnel release |
| D03 | Hydrocele | N43.3 (unspecified) | Hydrocele surgery |

Each bill has gross charges INR 30,000, discount INR 2,000, net INR 28,000, advance INR 10,000 and balance due INR 18,000. The reference codes are expected suggestions, not clinical coding decisions.

For a demonstration, use the Super Star policy wording in `../../healthcare/policy_fixtures/Policy_SuperStar.pdf`. Its PDF page 18 lists these conditions under a 24-month specified disease/procedure waiting period. Waiting periods may be changed by selected policy options or affected by prior coverage and other terms. A waiting-period result is not a claim approval. The co-payment depends on the applicable schedule and conditions.

These are intentionally easy, digitally readable examples. Successful results do not establish accuracy for other policies, diagnoses, layouts, scanned documents or real claims. Keep the earlier varied test cases to assess those limitations.

## Alternative formats

- **Scanned D01:** Use `D01_discharge_summary_scanned.pdf` and `D01_final_bill_scanned.pdf` together. These are image-only PDFs and require OCR. They contain the same fictional case as D01; use the scanned files instead of the digital D01 files, not in addition to them. Review the extracted values and confirm the scanned bill before calculating an estimate.
- **Combined D02:** Upload `D02_combined_discharge_and_bill.pdf` as one hospital document. Page 1 is the discharge summary; page 2 is the bill. It contains the same fictional case as the separate D02 files, so use one format or the other.

The OCR extraction was checked with the locally installed Tesseract. Actual scans can have different quality and may need correction.
