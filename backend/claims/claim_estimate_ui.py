"""Review and display saved claim estimates in Streamlit."""

import sqlite3
from decimal import Decimal

import streamlit as st

from backend.documents.bill_policy_evidence import match_expense_entries, read_expense_entries
from backend.documents.bill_items import daily_room_and_nursing
from backend.claims.claim_estimate import ReviewedDeduction, estimate_claim
from backend.storage.estimate_store import EstimateSnapshot, load_estimate_history, save_estimate


def show_claim_estimate(
    items, totals, rule, *, claim_id, bill_name, bill_hash, policy_name, policy_hash, policy_pages,
    room_limit=None, sum_insured=None, waiting_evidence=None,
):
    context = f"{claim_id}_{bill_hash}_{policy_hash}"
    identity = (claim_id, bill_hash, policy_hash)
    result_key = f"estimate_result_{context}"
    history = []
    if claim_id is not None:
        try:
            history = load_estimate_history(*identity)
        except (OSError, sqlite3.Error):
            st.error("Could not load the saved estimate history.")
    latest = history[0].snapshot if history else st.session_state.get(result_key)

    st.subheader("Estimate claim reimbursement")
    st.caption(
        "Review eligibility and enter any policy deductions after the hospital discount. "
        "The calculation uses the net bill."
    )
    if claim_id is None:
        st.caption("Draft estimates last for this session. Calculate on a saved claim to keep a revision history.")
    with st.expander(f"Co-payment evidence · Clause 9.5 · PDF page {rule.page}"):
        st.write(policy_name)
        st.text(rule.excerpt)
    entries = read_expense_entries(policy_pages)
    _show_deduction_evidence(items, entries, context)

    previous = {
        (deduction.item.page, deduction.item.number): deduction
        for deduction in latest.estimate.deductions
    } if latest else {}
    suggested = _suggest_deductions(items, entries, room_limit, sum_insured)
    if suggested:
        with st.expander("Suggested deductions to review"):
            st.table([
                {"Expense": deduction.item.description, "Bill PDF page": deduction.item.page,
                 "Suggested amount": str(deduction.amount), "Policy source": deduction.reason}
                for deduction in suggested.values()
            ])
            st.caption("Confirm the policy applies and adjust amounts for any hospital discount before calculating.")
    use_suggestions = bool(suggested) and st.checkbox(
        "Fill in suggested deductions for rows without a saved deduction",
        key=f"deduction_suggestions_{context}",
    )
    waiting_item = None
    if waiting_evidence:
        st.warning(waiting_evidence)
        waiting_item = st.selectbox(
            "Select an expense affected by the waiting period to add its source",
            items, index=None, format_func=lambda item: f"{item.number}. {item.description}",
            key=f"waiting_deduction_{context}",
        )
        st.caption("Enter the affected amount after reviewing the policy conditions and exceptions.")
    with st.form(f"estimate_form_{context}"):
        cover = st.number_input(
            "Reviewed remaining cover (₹)", min_value=0.0, step=100.0,
            value=float(latest.remaining_cover) if latest else None,
            key=f"estimate_cover_{context}",
        )
        table = []
        for item in items:
            row_key = (item.page, item.number)
            saved = previous.get(row_key) or (
                suggested.get(row_key) if use_suggestions and item != waiting_item else None
            )
            table.append({
                "Expense": f"{item.number}. {item.description}",
                "Bill page": item.page,
                "Printed charge (₹)": float(item.amount),
                "Deduct (₹)": float(saved.amount) if saved else 0.0,
                "Reason and policy source": saved.reason if saved else waiting_evidence if item == waiting_item else "",
            })
        entries = st.data_editor(
            table,
            disabled=["Expense", "Bill page", "Printed charge (₹)"],
            column_config={
                "Deduct (₹)": st.column_config.NumberColumn(min_value=0.0, step=0.01, format="%.2f"),
            },
            hide_index=True,
            key=f"estimate_deductions_{context}_{use_suggestions}_{waiting_item.number if waiting_item else 0}",
        )
        verified = st.checkbox("I reviewed eligibility, waiting periods, policy limits, and the amounts above.")
        submitted = st.form_submit_button("Calculate estimate")

    if submitted:
        if cover is None or not verified:
            st.warning("Enter the remaining cover and confirm the policy review before calculating.")
        else:
            try:
                adjustments = tuple(
                    ReviewedDeduction(
                        item, Decimal(str(entry["Deduct (₹)"])), entry["Reason and policy source"] or "",
                    )
                    for item, entry in zip(items, entries, strict=True)
                    if entry["Deduct (₹)"] not in {0, None}
                )
                remaining_cover = Decimal(str(cover))
                estimate = estimate_claim(totals.net.amount, remaining_cover, adjustments, rule)
            except ValueError as error:
                st.warning(str(error))
            else:
                snapshot = EstimateSnapshot(
                    estimate, remaining_cover, bill_name, totals.net.page, policy_name, rule,
                )
                if claim_id is None:
                    st.session_state[result_key] = latest = snapshot
                else:
                    try:
                        revision_id = save_estimate(*identity, snapshot)
                    except (OSError, sqlite3.Error):
                        st.error("Could not save this estimate. Check local storage and submit the review again.")
                        latest = snapshot
                    else:
                        latest = snapshot
                        st.success(f"Estimate saved · revision #{revision_id}")
                        try:
                            history = load_estimate_history(*identity)
                        except (OSError, sqlite3.Error):
                            st.warning("The estimate was saved. History could not be refreshed.")

    if latest is not None:
        st.caption("Based on the last calculated review.")
        _show_breakdown(latest)

    if history:
        with st.expander("Estimate history"):
            revisions = {revision.id: revision for revision in history}
            selected = st.selectbox(
                "Select a saved revision",
                list(revisions),
                format_func=lambda value: (
                    f"#{value} · {revisions[value].saved_at} UTC · "
                    f"₹{revisions[value].snapshot.estimate.payable:,.2f}"
                ),
                index=None,
                key=f"estimate_history_{context}",
            )
            if selected is not None:
                revision = revisions[selected]
                st.caption(f"Saved {revision.saved_at} UTC")
                _show_breakdown(revision.snapshot)
        return history[0]
    return None


def _suggest_deductions(items, entries, room_limit, sum_insured):
    suggestions = {}
    charges = daily_room_and_nursing(items)
    if charges and room_limit is not None and sum_insured is not None:
        room, nursing = charges
        excess = (room.rate + nursing.rate - room_limit.daily_limit(Decimal(sum_insured))) * room.quantity
        for item in charges:
            amount = min(excess, item.amount).quantize(Decimal("0.01"))
            if amount > 0:
                reason = f"Room and nursing charges above daily limit · Clause 4.1(a) · Policy PDF page {room_limit.page}"
                suggestions[item.page, item.number] = ReviewedDeduction(item, amount, reason)
                excess -= amount
    for item in items:
        exact, _ = match_expense_entries(item.description, entries)
        exclusions = [entry for entry in exact if entry.list_name.casefold() == "list i"
                      and "coverage is not available" in entry.list_title.casefold()]
        if len(exclusions) == 1 and item.amount > 0:
            suggestions.setdefault((item.page, item.number), ReviewedDeduction(
                item, item.amount, f"Listed non-payable item · {exclusions[0].citation}",
            ))
    return suggestions


def _show_deduction_evidence(items, entries, context):
    if not entries:
        return
    with st.expander("Find policy evidence for an expense"):
        item = st.selectbox(
            "Bill expense to review",
            items,
            index=None,
            format_func=lambda row: f"{row.number}. {row.description}",
            key=f"expense_evidence_row_{context}",
        )
        if item is None:
            return

        detail = st.text_input(
            "Item name from the detailed bill, if different",
            key=f"expense_evidence_detail_{context}_{item.page}_{item.number}",
        ).strip()
        search_text = detail or item.description
        exact, related = match_expense_entries(search_text, entries)
        st.caption(f"{item.description} · Bill PDF page {item.page} · ₹{item.amount:,.2f}")
        if detail:
            st.caption("Confirm the item and its individual amount on the detailed bill before entering a deduction.")
        if not exact and not related:
            st.info("No matching annexure item was found. Check the detailed bill and policy wording before classifying this charge.")
            return
        if exact:
            st.write("Matching policy labels")
        else:
            st.write("Related wording to review")
        for entry in (exact or related)[:8]:
            st.text(f"{entry.citation}\n{entry.list_title}\n{entry.description}")
        st.caption("Use the applicable citation in the deduction reason after reviewing the evidence.")


def _show_breakdown(snapshot: EstimateSnapshot):
    estimate = snapshot.estimate
    rule = snapshot.copayment_rule
    st.write(f"Reviewed remaining cover · ₹{snapshot.remaining_cover:,.2f}")
    rows = [{
        "Step": "Net bill after hospital discount",
        "Amount (₹)": f"{estimate.net_bill:,.2f}",
        "Source or reason": f"{snapshot.bill_name} · PDF page {snapshot.net_bill_page}",
    }]
    rows.extend({
        "Step": deduction.item.description,
        "Amount (₹)": f"−{deduction.amount:,.2f}",
        "Source or reason": f"Bill PDF page {deduction.item.page} · {deduction.reason}",
    } for deduction in estimate.deductions)
    rows.extend([
        {"Step": "Remaining-cover adjustment", "Amount (₹)": f"−{estimate.cover_limit_deduction:,.2f}", "Source or reason": "Reviewed remaining cover"},
        {"Step": "Admissible amount before co-payment", "Amount (₹)": f"{estimate.admissible_amount:,.2f}", "Source or reason": "Reviewed bill and policy adjustments"},
        {"Step": f"Co-payment ({rule.percent:g}%)", "Amount (₹)": f"−{estimate.copayment:,.2f}", "Source or reason": f"{snapshot.policy_name} · Clause 9.5 · PDF page {rule.page}"},
    ])
    st.table(rows)
    st.metric("Estimated reimbursement", f"₹{estimate.payable:,.2f}")
