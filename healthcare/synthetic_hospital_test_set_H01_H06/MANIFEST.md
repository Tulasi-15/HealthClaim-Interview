# Synthetic Indian Hospital Test Set (H01–H06)

All documents, patient identities, hospital names, registration numbers, dates, and financial figures are completely **fictional** and generated for software testing (`SYNTHETIC TEST DOCUMENT`).

## File & Case Manifest

| Case | Hospital | Files | Page Count & Reading Method | Document Groups & Test Focus |
| :--- | :--- | :--- | :--- | :--- |
| **H01** | Deccan Crest Medical Centre | `H01_final_bill.pdf`<br>`H01_discharge_summary.pdf` | 1p (`selectable_text`)<br>1p (`selectable_text`) | Separate single-page itemized bill + discharge summary with matching patient (`Ananya Krishnan`, `DC-10482`) and dates (`2026-07-02` to `2026-07-05`). |
| **H02** | Malabar Bay Institute of Health | `H02_final_bill.pdf` | 2p (`selectable_text`) | Multipage final bill (`MBIH/2026/08-1194`) with repeated table header, continued rows across pages 1–2, and final totals only on page 2. |
| **H03** | Vindhya Heights Hospital | `H03_final_bill_scanned.pdf`<br>`H03_discharge_summary.pdf` | 1p (`ocr_image_only`)<br>1p (`selectable_text`) | Image-only scanned bill (no embedded text layer) + digital discharge summary; distinct label vocabulary (`Voucher Ref`, `Beneficiary Name`, `MRN`) and column order. |
| **H04** | Coromandel Care & Surgical Guild | `H04_combined_claim_packet.pdf` | 4p (`selectable_text`) | Combined PDF: p.1 `discharge_summary`, pp.2–3 `final_bill` (with explicit continuation header on p.3), p.4 `lab_report`. |
| **H05** | Kaveri Valley Hospital & Dispensary | `H05_hospital_bill.pdf`<br>`H05_pharmacy_tax_invoice.pdf` | 1p (`selectable_text`)<br>1p (`selectable_text`) | Hospital bill + pharmacy `Tax Invoice` (`KVH-PH-2026-3109`, net ₹4,200.00) that itemizes the ₹4,200.00 pharmacy line in the hospital bill (must be counted once). |
| **H06** | Narmada Diagnostic & General Clinic | `H06_final_bill.pdf`<br>`H06_lab_report.pdf` | 1p (`selectable_text`)<br>1p (`selectable_text`) | Compact bill with side-block totals, unnumbered rows, explicit `0.00` discount vs. `null` absent `procedure` field, plus standalone lab report. |

## Ground Truth
- `answer_keys.json` contains structured ground-truth records for all six cases (`H01` through `H06`), including physical page numbers, itemized charges, totals, `review_flags`, and `fixture_notes`.
