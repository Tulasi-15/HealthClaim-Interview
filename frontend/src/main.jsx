import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const money = (value) => value == null || value === "" ? "—" :
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value));

async function api(path, body, method = "POST") {
  const upload = body instanceof FormData;
  const response = await fetch("/api" + path, body === undefined && method === "POST" ? {} : {
    method,
    headers: { "X-Claims-Client": "react", ...(upload ? {} : { "Content-Type": "application/json" }) },
    body: upload ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    const error = new Error(Array.isArray(detail) ? detail.map(item => item.msg).join(". ") :
      detail || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(callback) {
    setBusy(true);
    setError("");
    try { return await callback(); }
    catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  }
  return { busy, error, run, clearError: () => setError("") };
}

function ErrorText({ message }) {
  return message ? <p className="error" role="alert">{message}</p> : null;
}

function SignIn({ onLogin, themeToggle }) {
  const [register, setRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [notice, setNotice] = useState("");
  const action = useAction();
  const googleButton = useRef(null);
  const [googleError, setGoogleError] = useState("");
  useEffect(() => {
    let active = true;
    let script;
    let observer;
    async function setupGoogle() {
      const config = await api("/auth/google/config");
      if (!active || !config.client_id) return;
      const challenge = await api("/auth/google/challenge", {});
      if (!active) return;
      script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = () => {
        if (!active || !googleButton.current) return;
        window.google.accounts.id.initialize({
          client_id: config.client_id,
          nonce: challenge.nonce,
          callback: async response => {
            try {
              await api("/auth/google", { credential: response.credential });
              if (active) onLogin();
            } catch (error) {
              if (active) setGoogleError(error.message + " Refresh the page to retry.");
            }
          },
        });
        let lastWidth = 0;
        const renderButton = () => {
          if (!active || !googleButton.current) return;
          const width = Math.min(400, Math.floor(googleButton.current.clientWidth));
          if (width <= 0 || width === lastWidth) return;
          lastWidth = width;
          googleButton.current.replaceChildren();
          window.google.accounts.id.renderButton(googleButton.current, {
            type: "standard", theme: "outline", size: "large", text: "continue_with", width,
          });
        };
        observer = new ResizeObserver(renderButton);
        observer.observe(googleButton.current);
        renderButton();
      };
      script.onerror = () => { if (active) setGoogleError("Google sign-in could not load."); };
      document.head.appendChild(script);
    }
    setupGoogle().catch(error => { if (active) setGoogleError(error.message); });
    return () => { active = false; observer?.disconnect(); script?.remove(); };
  }, []);
  function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    action.run(async () => {
      const credentials = { email: form.get("email"), password: form.get("password") };
      if (register && credentials.password !== form.get("confirm")) throw new Error("The passwords do not match.");
      try {
        await api(register ? "/signup" : "/login", credentials);
      } catch (error) {
        if (register && error.status === 409) {
          throw new Error("An account already exists for this email. Please sign in.");
        }
        throw error;
      }
      if (register) {
        setNotice("Account created. Sign in to open your workspace.");
        setRegister(false);
        setShowPassword(false);
      } else onLogin();
    });
  }
  return <>
    <div className="auth-theme">{themeToggle}</div>
    <main className="auth-layout">
    <section className="auth-intro">
      <Brand />
      <h1>Understand your health insurance claim.</h1>
      <p>Read your policy, check hospital charges, and see what supports an estimated reimbursement.</p>
    </section>
    <section className="card auth-card">
      <h2>{register ? "Create your account" : "Sign in"}</h2>
      {notice && <p className="success" role="status">{notice}</p>}
      <form onSubmit={submit} key={register}>
        <label>Email<input name="email" type="email" autoComplete="username" maxLength={254} required /></label>
        <label>Password<input name="password" type={register && showPassword ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"}
          minLength={register ? 12 : 1} maxLength={256} required /></label>
        {register && <>
          <label>Confirm password<input name="confirm" type={showPassword ? "text" : "password"}
            autoComplete="new-password" required /></label>
          <label className="check"><input type="checkbox" checked={showPassword}
            onChange={event => setShowPassword(event.target.checked)} /> Show passwords</label>
        </>}
        <ErrorText message={action.error} />
        <button disabled={action.busy}>{action.busy ? "Please wait…" : register ? "Create account" : "Sign in"}</button>
      </form>
      <div className="google-signin" ref={googleButton} />
      <ErrorText message={googleError} />
      <button className="text-button" onClick={() => {
        setNotice(""); action.clearError(); setShowPassword(false); setRegister(!register);
      }}>
        {register ? "Already have an account? Sign in" : "New here? Create an account"}
      </button>
    </section>
    </main>
  </>;
}

function Brand() {
  return <div className="brand"><span aria-hidden="true">+</span> Claims Assist</div>;
}

function Upload({ label, files, onFiles, multiple }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState("");
  function accept(list) {
    const chosen = Array.from(list);
    if (chosen.some(file => !file.name.toLowerCase().endsWith(".pdf"))) {
      setError("Choose PDF files."); return;
    }
    setError("");
    onFiles(multiple ? chosen : chosen.slice(0, 1));
  }
  return <div>
    <input ref={input} hidden type="file" accept="application/pdf,.pdf" multiple={multiple}
      aria-label={label} onChange={event => accept(event.target.files)} />
    <button type="button" className={"dropzone" + (over ? " over" : "")}
      onClick={() => input.current.click()} onDragOver={event => { event.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)} onDrop={event => { event.preventDefault(); setOver(false); accept(event.dataTransfer.files); }}>
      <span className="upload-mark" aria-hidden="true">↑</span>
      <span>{files.length ? files.map(file => file.name).join(", ") : label}</span>
      <small>{files.length ? "Browse to replace selection" : "Drag and drop or browse"}</small>
    </button>
    {files.length > 0 && <button type="button" className="text-button" onClick={() => { input.current.value = ""; onFiles([]); }}>Clear selection</button>}
    <ErrorText message={error} />
  </div>;
}

function PdfPreview({ claim, source }) {
  const [show, setShow] = useState(false);
  return <div className="preview">
    <button type="button" className="text-button" aria-expanded={show}
      onClick={() => setShow(!show)}>{show ? "Hide" : "Show"} PDF page {source.page}</button>
    {show && <img alt={`Source PDF page ${source.page}`} src={`/api/claims/${claim}/documents/${source.document}/pages/${source.page}`} />}
  </div>;
}

function Chat({ id, hasPolicy, doc, group, ready, summary }) {
  const [open, setOpen] = useState(false);
  const launcher = useRef(null);
  const closeButton = useRef(null);
  const [history, setHistory] = useState([]);
  const messages = useRef(null);
  const [historyError, setHistoryError] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(Boolean(id));
  const [question, setQuestion] = useState("");
  const action = useAction();
  useEffect(() => {
    if (!id) return;
    let active = true;
    api(`/claims/${id}/chat`).then(turns => {
      if (active) setHistory(turns);
    }).catch(error => {
      if (active) setHistoryError(error.message);
    }).finally(() => {
      if (active) setLoadingHistory(false);
    });
    return () => { active = false; };
  }, [id]);
  useEffect(() => {
    if (open && messages.current) messages.current.scrollTop = messages.current.scrollHeight;
  }, [history, open]);
  useEffect(() => {
    if (open) closeButton.current?.focus();
  }, [open]);
  function closeChat() {
    setOpen(false);
    launcher.current?.focus();
  }
  function submit(event) {
    event.preventDefault();
    const text = question.trim();
    if (!text) return;
    action.run(async () => {
      const answer = await api(`/claims/${id}/chat`, {
        question: text, semantic: ready, document: doc, start_page: group,
        summary_document: summary?.document, summary_page: summary?.page,
      });
      setHistory(previous => [...previous, { question: text, ...answer }]);
      setQuestion("");
    });
  }
  return <div className="floating-chat" onKeyDown={event => {
    if (open && event.key === "Escape") {
      event.stopPropagation();
      closeChat();
    }
  }}>
    <section id="claim-chat" className="card chat-card" hidden={!open} aria-labelledby="claim-chat-title">
      <div className="section-heading">
        <h2 id="claim-chat-title">Claim assistant</h2>
        <button ref={closeButton} type="button" className="secondary chat-close"
          onClick={closeChat} aria-label="Close claim assistant">×</button>
      </div>
    {!hasPolicy && doc == null && !summary ? <p className="muted">Upload a policy or hospital document to start.</p> : <>
      {!history.length && <div className="chat-empty">
        <p>Ask about your hospital documents, policy, or saved estimate.</p>
        <div className="chips">
          {["What is the daily room rent limit?", "What is the waiting period for cataract surgery?", "How much will I get back?"]
            .map(text => <button type="button" className="chip" key={text} onClick={() => setQuestion(text)}>{text}</button>)}
        </div>
      </div>}
      <div className="messages" ref={messages} aria-live="polite">
        {history.map(turn => <div key={turn.id} className="turn">
          <div className="question">{turn.question}</div>
          <div className="answer">{turn.text.replaceAll("**", "")}</div>
          {turn.sources.map((source, number) => {
            const page = source.citation.match(/PDF page (\d+)/i);
            const policySource = !/^(?:Bill|Hospital) PDF page /i.test(source.citation);
            return <details className="citation" key={number}><summary>{source.citation}</summary>
              {source.document_name && <small>{source.document_name}</small>}
              <p>{source.excerpt}</p>
              {page && (policySource || source.hospital_document != null || turn.bill_document != null) &&
                <PdfPreview claim={id} source={{ document: policySource ? -1 : source.hospital_document ?? turn.bill_document, page: Number(page[1]) }} />}
            </details>;
          })}
        </div>)}
      </div>
      <form className="chat-form" onSubmit={submit}>
        <input aria-label="Ask a question" value={question} onChange={event => setQuestion(event.target.value)}
          placeholder="Ask about your claim…" maxLength={500} required />
        <button disabled={loadingHistory || action.busy || !question.trim()}>{action.busy ? "Checking…" : "Send"}</button>
      </form>
      <ErrorText message={action.error} />
      <ErrorText message={historyError} />
    </>}
    </section>
    <button ref={launcher} type="button" className="chat-launcher"
      aria-label={open ? "Close claim assistant" : "Open claim assistant"}
      aria-expanded={open} aria-controls="claim-chat"
      onClick={() => open ? closeChat() : setOpen(true)}>
      <span className="chat-launcher-icon" aria-hidden="true" />
    </button>
  </div>;
}

const totalLabels = { gross: "Gross bill", discount: "Discount", net: "Net bill", advance: "Advance paid", balance: "Balance due" };

function ClaimSection({ title, className = "", initiallyOpen = false, children }) {
  return <details className="card claim-section" open={initiallyOpen || undefined}>
    <summary><h2>{title}</h2><span className="section-chevron" aria-hidden="true" /></summary>
    <div className={`claim-section-body ${className}`}>{children}</div>
  </details>;
}

function BillReview({ claim, doc, group, bill, refresh, onDirty }) {
  const savedTotals = () => Object.fromEntries(Object.keys(totalLabels).map(key => [key, {
    amount: bill.totals?.[key]?.amount ?? "", page: bill.totals?.[key]?.page ?? "",
  }]));
  const [totals, setTotals] = useState(savedTotals);
  const [rows, setRows] = useState(bill.items);
  const [editing, setEditing] = useState(false);
  const [showCharges, setShowCharges] = useState(false);
  const [dirty, setDirty] = useState({ rows: false, totals: false });
  const action = useAction();
  const pending = dirty.rows || dirty.totals;
  const pageNumbers = [...new Set([...rows.map(row => row.page),
    ...Object.values(totals).map(total => Number(total.page)).filter(Boolean)])].sort((a, b) => a - b);
  const url = `/claims/${claim}/documents/${doc}/review`;

  async function save() {
    if (!pending || action.busy) return;
    await action.run(async () => {
      const payload = {};
      if (dirty.rows) {
        if (rows.some(row => !Number.isInteger(Number(row.quantity)) || Number(row.quantity) < 1 ||
          row.rate === "" || row.amount === "" || Number(row.rate) < 0 || Number(row.amount) < 0))
          throw new Error("Enter valid quantities, rates, and amounts before continuing.");
        payload.rows = rows.map(({ quantity, rate, amount }) => ({ quantity: Number(quantity), rate, amount }));
      }
      if (dirty.totals) {
        payload.totals = Object.fromEntries(Object.entries(totals).map(([name, value]) => [name, {
          amount: value.amount === "" ? null : value.amount,
          page: value.amount === "" ? null : (Number(value.page) || (bill.page_count === 1 ? 1 : null)),
        }]));
      }
      await api(url, { ...payload, start_page: group, identity: bill.identity });
      await refresh();
      setDirty({ rows: false, totals: false });
      onDirty(false);
    });
  }
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(save, 750);
    return () => clearTimeout(timer);
  }, [rows, totals, pending]);

  function change(kind, update) {
    update();
    setDirty(previous => ({ ...previous, [kind]: true }));
    onDirty(true);
  }

  const totalValue = key => editing ? <span className="total-edit">
    <input aria-label={totalLabels[key]} type="number" min="0" step="0.01"
      value={totals[key].amount} onChange={event => change("totals", () =>
        setTotals({ ...totals, [key]: { ...totals[key], amount: event.target.value } }))} />
    {bill.page_count > 1 && totals[key].amount !== "" && !bill.totals?.[key]?.page &&
      <input aria-label={totalLabels[key] + " source page"} placeholder="PDF page" type="number"
        min="1" max={bill.page_count} value={totals[key].page} onChange={event => change("totals", () =>
          setTotals({ ...totals, [key]: { ...totals[key], page: event.target.value } }))} />}
  </span> : <strong>{money(totals[key].amount)}</strong>;

  return <ClaimSection title="Bill summary" className="bill-summary">
    <div className="section-heading bill-summary-actions"><div className="actions">
      <button type="button" className={editing ? "secondary" : "edit-icon"}
        aria-label={editing ? "Done editing bill summary" : "Edit bill summary"}
        title={editing ? "Done editing" : "Edit bill summary"}
        disabled={action.busy || (editing && pending)} onClick={() => setEditing(!editing)}>
        {editing ? "Done editing" : <span aria-hidden="true">✏︎</span>}
      </button>
      <button type="button" className={bill.accepted && !pending ? "bill-reviewed" : "secondary"}
        disabled={action.busy || pending || bill.accepted || !rows.length}
        onClick={() => action.run(async () => {
          await api(url, { start_page: group, accept: true, identity: bill.identity });
          await refresh();
        })}>{bill.accepted && !pending ? "✓ Reviewed" : "Mark as reviewed"}</button>
    </div></div>
    {bill.scanned && !bill.accepted && <p className="notice">Check the scanned bill against the original before accepting.</p>}
    {editing && <p className="muted" role="status">{action.busy ? "Saving changes…" : pending ? "Changes pending" : "Edits save automatically."}</p>}
    {editing && pending && action.error && <button type="button" className="text-button" onClick={() => {
      setRows(bill.items);
      setTotals(savedTotals());
      setDirty({ rows: false, totals: false });
      onDirty(false);
      action.clearError();
    }}>Discard unsaved edits</button>}
    <fieldset disabled={action.busy} className="bill-values">
      <div className="gross-line bill-line">
        <div><span>Gross bill</span>
          <button type="button" className="bill-charges-button" aria-expanded={showCharges}
            aria-controls="bill-itemized-charges" onClick={() => setShowCharges(!showCharges)}>
            {showCharges ? "Hide itemized charges" : "View itemized charges"}
            {" "}<span aria-hidden="true">{showCharges ? "▴" : "▾"}</span>
          </button>
        </div>
        {totalValue("gross")}
      </div>
      <div className="bill-charges" id="bill-itemized-charges" hidden={!showCharges}>
        {showCharges && (rows.length ? <div className="table-wrap"><table>
          <thead><tr><th scope="col">Charge</th><th scope="col">Qty</th><th scope="col">Rate (₹)</th><th scope="col">Amount (₹)</th></tr></thead>
          <tbody>{rows.map((row, index) => <tr key={row.number} className={Math.abs(Number(row.quantity) * Number(row.rate) - Number(row.amount)) > .001 ? "row-warning" : ""}>
            <th scope="row">{row.description}<small>{row.unit || "unit"}</small></th>
            {["quantity", "rate", "amount"].map(field => <td key={field}>{editing ?
              <input aria-label={`Row ${row.number} ${field}`} type="number" min={field === "quantity" ? 1 : 0}
                step={field === "quantity" ? 1 : ".01"} value={row[field]} onChange={event =>
                  change("rows", () => setRows(rows.map((item, i) => i === index ? { ...item, [field]: event.target.value } : item)))} />
              : field === "quantity" ? row[field] : money(row[field])}</td>)}
          </tr>)}</tbody>
        </table></div> : <p className="muted">No complete expense table was found.</p>)}
      </div>
      {Object.keys(totalLabels).slice(1).map(key => <div className={`gross-line bill-line bill-line-${key}`} key={key}>
        <span>{totalLabels[key]}</span>{totalValue(key)}
      </div>)}
    </fieldset>
    <details><summary>Original bill pages</summary>
      {pageNumbers.map(page => <PdfPreview key={page} claim={claim} source={{ document: doc, page }} />)}
    </details>
    <ErrorText message={action.error} />
  </ClaimSection>;
}
function ClaimDetails({ claim, document, bill, summaryPage = null, onDiagnosisChange, children }) {
  const [diagnosis, setDiagnosis] = useState(() =>
    bill.reviewed_clinical["Primary diagnosis"] ?? bill.findings["Primary diagnosis"]?.text ?? "");
  const [editingDiagnosis, setEditingDiagnosis] = useState(false);
  const [mapping, setMapping] = useState(null);
  const [choice, setChoice] = useState("");
  const [editingCode, setEditingCode] = useState(false);
  const action = useAction();
  const path = `/claims/${claim}/documents/${document}`;
  useEffect(() => {
    let active = true;
    api(path + "/diagnosis" + (summaryPage ? `?summary_page=${summaryPage}` : "")).then(result => {
      if (active) {
        setMapping(result);
        setChoice(result.status === "confirmed" ? result.code : "");
      }
    }).catch(() => {});
    return () => { active = false; };
  }, [path, summaryPage, diagnosis]);
  const procedure = bill.reviewed_clinical["Procedure performed"] ?? bill.findings["Procedure performed"]?.text ?? "";
  function choose(code) {
    action.run(async () => {
      await api(path + "/clinical", { diagnosis: mapping.diagnosis, procedure, icd10_code: code || null,
        summary_page: summaryPage });
      setChoice(code);
      setEditingCode(false);
    });
  }
  const fields = Object.assign({}, ...Object.values(bill?.fields || {}));
  const showCodePicker = mapping && (editingCode || (!choice && mapping.candidates.length > 1));
  const displayCode = choice || mapping?.code;
  return <ClaimSection title="Extracted claim details" className="claim-details" initiallyOpen>
    <dl className="fields">{Object.entries(fields).filter(([key]) => key !== "Primary diagnosis").map(([label, value]) =>
      <React.Fragment key={label}><dt>{label}</dt><dd>{value.text}</dd></React.Fragment>)}
      <dt>Diagnosis</dt><dd>
        {editingDiagnosis ? <form className="diagnosis-editor" onSubmit={event => {
          event.preventDefault();
          const updated = String(new FormData(event.currentTarget).get("diagnosis")).trim();
          if (updated === diagnosis) { setEditingDiagnosis(false); return; }
          action.run(async () => {
            await api(path + "/clinical", { diagnosis: updated, procedure, summary_page: summaryPage });
            setMapping(null);
            setChoice("");
            setEditingCode(false);
            setDiagnosis(updated);
            setEditingDiagnosis(false);
            onDiagnosisChange();
          });
        }}>
          <input name="diagnosis" aria-label="Diagnosis" defaultValue={diagnosis} maxLength={1000} autoFocus />
          <div className="diagnosis-editor-actions">
            <button disabled={action.busy}>Save</button>
            <button type="button" className="secondary" disabled={action.busy}
              onClick={() => setEditingDiagnosis(false)}>Cancel</button>
          </div>
        </form> : <>
          <span>{diagnosis || "Diagnosis not found"}</span>
          <button type="button" className="edit-icon" aria-label="Edit diagnosis" title="Edit diagnosis"
            disabled={action.busy} onClick={() => setEditingDiagnosis(true)}><span aria-hidden="true">✏︎</span></button>
        </>}
      </dd>
      {mapping?.diagnosis && <><dt>Diagnosis code</dt><dd>
        {showCodePicker ? <>
          <select aria-label="Diagnosis code" disabled={action.busy}
          value={choice || (editingCode ? displayCode || "" : "")} onChange={event => choose(event.target.value)}>
          <option value="" disabled>Choose a code</option>
          {choice && !mapping.candidates.some(item => item.code === choice) && <option value={choice}>{choice}</option>}
          {mapping.candidates.map(item => <option key={item.code} value={item.code}>{item.code} · {item.description}</option>)}
          </select>
          {editingCode && <button type="button" disabled={action.busy} onClick={() => setEditingCode(false)}>Cancel</button>}
        </> : displayCode ? <>
          <span>{displayCode}</span>{" "}
          {mapping.candidates.some(item => item.code !== displayCode) &&
            <button type="button" className="edit-icon" aria-label="Edit diagnosis code" title="Edit diagnosis code"
              onClick={() => setEditingCode(true)}><span aria-hidden="true">✏︎</span></button>}
        </> :
          <small>No reliable code found. You can continue using the diagnosis wording.</small>}
      </dd></>}
    </dl>
    <ErrorText message={action.error} />
    {children(diagnosis, procedure)}
  </ClaimSection>;
}
function PolicyLimitCheck({ observations }) {
  const [confirmed, setConfirmed] = useState(false);
  return <section className="policy-comparison">
    <h3>Compare waiting periods with{" "}
      <a href="https://egazette.gov.in/WriteReadData/2024/253325.pdf" target="_blank" rel="noopener noreferrer">IRDAI</a>
      {" "}limits
    </h3>
    <p className="muted">This compares the identified wording with the 36-month limit, where the 2024 regulation applies.</p>
    {observations.length ? <>
      <label className="check"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />
        I checked the policy version and the cited clauses, and confirmed that this limit applies.</label>
      <div className="table-wrap"><table>
        <thead><tr><th>Waiting period</th><th>Policy</th><th>IRDAI maximum</th><th>Result</th></tr></thead>
        <tbody>{observations.map(item => <tr key={`${item.type}:${item.months}`}>
          <th>{item.type}</th><td>{item.months} months
            <small>Stated on PDF {item.pages.length === 1 ? "page" : "pages"} {item.pages.join(", ")}</small>
          </td>
          <td>36 months</td><td>{!confirmed ? "Needs review" : item.months > 36 ? "Appears to exceed limit" : "Within limit"}</td>
        </tr>)}</tbody>
      </table></div>
    </> : <p className="notice">Needs review. We couldn’t verify a waiting period from the uploaded wording.</p>}
  </section>;
}

function IrdaiReferences() {
  const [entries, setEntries] = useState(null);
  const action = useAction();
  function loadReferences() {
    action.run(async () => setEntries(await api("/references/irdai")));
  }
  return <details className="irdai-references" onToggle={event => {
    if (event.currentTarget.open && !entries && !action.busy) loadReferences();
  }}>
    <summary>IRDAI health insurance references</summary>
    <p className="muted">Use these documents alongside your uploaded policy when reviewing deductions.</p>
    {action.busy && <p role="status">Loading references…</p>}
    {entries?.length > 0 && <ul className="reference-list">{entries.map(entry => <li key={entry.id}>
      <div className="reference-copy">
        <strong>{entry.title}</strong>
        <small>{entry.reference}</small>
      </div>
      <a className="reference-link" href={`/api/references/irdai/${entry.id}${entry.id === "expenses-2019" ? "#page=2" : ""}`}
        target="_blank" rel="noopener noreferrer" aria-label={`Open PDF in a new tab: ${entry.title}`}>
        Open PDF <span aria-hidden="true">↗</span>
      </a>
    </li>)}</ul>}
    <ErrorText message={action.error} />
    {action.error && <button type="button" className="secondary" onClick={loadReferences}>Retry</button>}
  </details>;
}

function PolicyStartPicker({ initialDate, admissionDate }) {
  const [value, setValue] = useState(initialDate || "");
  const [open, setOpen] = useState(true);
  const [month, setMonth] = useState(() => (initialDate && (!admissionDate || initialDate <= admissionDate) ? initialDate : admissionDate || new Date().toISOString().slice(0, 10)).slice(0, 7));
  const toggle = useRef(null);
  const dateInput = useRef(null);
  const parsed = new Date(`${value}T00:00:00Z`);
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(value) && !value.startsWith("0000-")
    && !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  useEffect(() => {
    dateInput.current.setCustomValidity(!value ? "" : !validDate
      ? "Enter a valid date in YYYY-MM-DD format."
      : admissionDate && value > admissionDate ? "Policy start date must be on or before admission." : "");
  }, [value, validDate, admissionDate]);
  const first = new Date(`${month}-01T00:00:00Z`);
  const offset = (first.getUTCDay() + 6) % 7;
  const shiftMonth = amount => {
    const shifted = new Date(first);
    shifted.setUTCMonth(shifted.getUTCMonth() + amount);
    setMonth(shifted.toISOString().slice(0, 7));
  };
  const last = new Date(first);
  last.setUTCMonth(last.getUTCMonth() + 1, 0);
  const monthFormatter = new Intl.DateTimeFormat("en-IN", { month: "long", timeZone: "UTC" });
  const dayFormatter = new Intl.DateTimeFormat("en-IN", { dateStyle: "full", timeZone: "UTC" });
  const [year, monthNumber] = month.split("-");
  const [admissionYear, admissionMonth] = (admissionDate || "9999-12-31").split("-");
  return <div className="policy-start-picker" onKeyDown={event => {
    if (open && event.key === "Escape") {
      event.stopPropagation();
      setOpen(false);
      toggle.current?.focus();
    }
  }}>
    <label htmlFor="coverage-start">Policy start date</label>
    <div className="calendar-input-row">
      <input ref={dateInput} id="coverage-start" name="coverage" type="text" value={value}
        placeholder="YYYY-MM-DD" maxLength={10} required aria-describedby="coverage-start-help"
        onChange={event => setValue(event.target.value)} />
      <button ref={toggle} type="button" className="secondary calendar-toggle"
        aria-expanded={open} aria-controls="coverage-calendar" onClick={() => {
          if (!open) setMonth((validDate && (!admissionDate || value <= admissionDate) ? value : admissionDate || new Date().toISOString().slice(0, 10)).slice(0, 7));
          setOpen(!open);
        }}>Calendar</button>
    </div>
    <small id="coverage-start-help">Use the date your continuous coverage began.</small>
    {open && <div id="coverage-calendar" className="coverage-calendar" aria-label="Choose policy start date">
      <div className="calendar-navigation">
        <button type="button" className="secondary" onClick={() => shiftMonth(-1)}
          disabled={month === "0001-01"} aria-label="Previous month">‹</button>
        <select aria-label="Calendar month" value={monthNumber} onChange={event => setMonth(`${year}-${event.target.value}`)}>
          {Array.from({ length: 12 }, (_, index) => {
            const number = String(index + 1).padStart(2, "0");
            const date = new Date(`2000-${number}-01T00:00:00Z`);
            return <option key={number} value={number} disabled={year === admissionYear && number > admissionMonth}>
              {monthFormatter.format(date)}
            </option>;
          })}
        </select>
        <input key={year} aria-label="Calendar year" type="number" min="1" max={admissionYear} step="1"
          defaultValue={Number(year)} onBlur={event => {
            const next = event.target.valueAsNumber;
            if (!Number.isInteger(next) || next < 1 || next > Number(admissionYear)) {
              event.target.value = Number(year);
              return;
            }
            const nextYear = String(next).padStart(4, "0");
            const nextMonth = nextYear === admissionYear && monthNumber > admissionMonth ? admissionMonth : monthNumber;
            setMonth(`${nextYear}-${nextMonth}`);
          }} onKeyDown={event => {
            if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); }
          }} />
        <button type="button" className="secondary" onClick={() => shiftMonth(1)}
          disabled={Boolean(admissionDate && month >= admissionDate.slice(0, 7)) || month === "9999-12"} aria-label="Next month">›</button>
      </div>
      <div className="calendar-days">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(day => <span key={day}>{day}</span>)}
        {Array.from({ length: offset }, (_, index) => <span key={`empty-${index}`} aria-hidden="true" />)}
        {Array.from({ length: last.getUTCDate() }, (_, index) => {
          const day = index + 1;
          const iso = `${month}-${String(day).padStart(2, "0")}`;
          return <button key={iso} type="button" disabled={Boolean(admissionDate && iso > admissionDate)} aria-pressed={iso === value}
            aria-label={dayFormatter.format(new Date(`${iso}T00:00:00Z`))} onClick={() => {
              setValue(iso);
              setOpen(false);
              toggle.current?.focus();
            }}>{day}</button>;
        })}
      </div>
    </div>}
  </div>;
}

function WaitingReview({ id, bill, diagnosis, procedure, policy, coverageStart, onCoverageStart, onFinding, mismatch }) {
  const [editingWaiting, setEditingWaiting] = useState(false);
  const [editingStart, setEditingStart] = useState(false);
  const dateDialog = useRef(null);
  const [policyEvidence, setPolicyEvidence] = useState(null);
  const [evidenceError, setEvidenceError] = useState("");
  const [clause, setClause] = useState("");
  const [result, setResult] = useState(null);
  const [checkingSavedDate, setCheckingSavedDate] = useState(false);
  const [savedDateError, setSavedDateError] = useState("");
  const action = useAction();
  const admissionDate = Object.assign({}, ...Object.values(bill?.fields || {}))["Admission date"]?.normalized;
  const canLookUp = Boolean(policy && diagnosis && !mismatch);
  useEffect(() => {
    if (!canLookUp) {
      setResult(null);
      onFinding(null);
    }
  }, [canLookUp, onFinding]);
  useEffect(() => {
    let active = true;
    setPolicyEvidence(null);
    setEvidenceError("");
    setClause("");
    if (!canLookUp) return;
    api(`/claims/${id}/policy/diagnosis-evidence`, { diagnosis, procedure }).then(evidence => {
      if (!active) return;
      setPolicyEvidence(evidence);
      if (evidence.waiting_suggestions.length === 1 && evidence.waiting_suggestions[0].clause) {
        setClause(evidence.waiting_suggestions[0].clause);
      }
    }).catch(error => { if (active) setEvidenceError(error.message); });
    return () => { active = false; };
  }, [id, canLookUp, diagnosis, procedure]);
  const suggestions = policyEvidence?.waiting_suggestions || [];
  const datedRules = suggestions.filter(item => item.clause);
  const durations = [...new Set(suggestions.map(item => item.duration || `${item.months} months`))];
  const aiSuggestion = suggestions.find(item => item.ai);
  const manualWaiting = suggestions.find(item => item.manual);
  const savedWaiting = manualWaiting || aiSuggestion;
  const singleWaiting = suggestions.length === 1 ? suggestions[0] : null;
  const canCheckDates = Boolean(canLookUp && admissionDate && (datedRules.length || savedWaiting?.suggestion_id));
  const automaticClause = datedRules.length === 1 ? datedRules[0].clause : "";
  const automaticSuggestionId = singleWaiting?.suggestion_id;
  const automaticManual = Boolean(manualWaiting);
  const hasCurrentResult = result?.coverage_start === coverageStart && result?.admission === admissionDate;
  useEffect(() => {
    setCheckingSavedDate(false);
    setSavedDateError("");
    if (!canCheckDates || !coverageStart || editingStart || editingWaiting || hasCurrentResult ||
        (!automaticClause && !automaticSuggestionId)) return;
    if (coverageStart > admissionDate) {
      setSavedDateError("The saved policy start date is after admission. Enter an earlier date.");
      return;
    }
    let active = true;
    setCheckingSavedDate(true);
    api(`/claims/${id}/policy/waiting-check`, {
      clause: automaticClause, suggestion_id: automaticSuggestionId, manual: automaticManual,
      diagnosis, use_saved_start: true, admission: admissionDate, confirmed: Boolean(automaticClause || automaticManual),
    }).then(check => {
      if (!active) return;
      setResult({ ...check, admission: admissionDate });
      onCoverageStart(check.coverage_start);
      onFinding(check.met || check.provisional ? null : check.reason);
    }).catch(error => { if (active) setSavedDateError(error.message); })
      .finally(() => { if (active) setCheckingSavedDate(false); });
    return () => { active = false; };
  }, [id, canCheckDates, coverageStart, admissionDate, diagnosis, automaticClause, automaticSuggestionId, automaticManual,
      editingStart, editingWaiting, hasCurrentResult, onCoverageStart, onFinding]);
  const checkHint = mismatch ? "The hospital documents need review before checking dates."
    : !policy ? "Upload a policy to check the waiting period."
    : !diagnosis ? "Add a diagnosis to look up its waiting period."
    : !admissionDate ? "An admission date is needed from the hospital documents."
    : "Find or enter a waiting period to check the dates.";
  const waitingValue = durations.length ? durations.join(" / ")
    : mismatch ? "Check the selected documents"
    : !policy ? "Upload a policy to check"
    : !diagnosis ? "Diagnosis not available"
    : policyEvidence?.waiting_ai_unavailable ? "AI lookup unavailable"
    : evidenceError || policyEvidence ? "Could not verify"
    : "Checking…";
  return <div className="waiting-review">
    <div className="waiting-panel">
    <section className="waiting-summary" aria-label="Waiting period">
      <div className="waiting-summary-copy" aria-live="polite">
        <div className="waiting-summary-heading">
          <h3>Waiting period</h3>
          <span className={durations.length ? "waiting-duration" : "waiting-status"}>{waitingValue}</span>
        </div>
        {aiSuggestion && <small>AI suggestion · {aiSuggestion.citation}</small>}
        {manualWaiting && <small>Entered by you</small>}
      </div>
      {canLookUp && (policyEvidence || evidenceError) && !editingWaiting &&
        <button type="button" className="edit-icon" aria-label="Edit waiting period" title="Edit waiting period"
          disabled={action.busy} onClick={() => setEditingWaiting(true)}>
          <span aria-hidden="true">✏︎</span>
        </button>}
    </section>
    <section className={`waiting-outcome${result ? result.met ? " waiting-met" : " waiting-unmet" : ""}`}
      aria-label="Waiting-period check">
      <h3>Waiting-period check</h3>
      {result && <div role="status">
        <strong>{result.met ? "Waiting period met" : "Waiting period not met"}</strong>
        <small>{result.met ? "The period had ended by admission." : "The period was still active at admission."}
          {" "}Completion date {result.completes}.</small>
        {result.provisional && <small>{result.manual ? "Based on your entered duration."
          : result.confirmed ? "Based on the AI suggestion you confirmed." : "Provisional result based on an AI suggestion."}</small>}
      </div>}
      {coverageStart && <small>Saved policy start date {coverageStart}</small>}
      {checkingSavedDate && <small role="status">Checking saved start date…</small>}
      <ErrorText message={savedDateError} />
      {policy && <button type="button" className="secondary" aria-haspopup="dialog"
        aria-controls="waiting-date-dialog" disabled={checkingSavedDate}
        onClick={() => {
          action.clearError();
          setEditingStart(true);
          dateDialog.current.showModal();
        }}>{result ? "Change policy start date"
          : coverageStart ? "Check saved start date" : "Enter policy start date"}</button>}
      {!canCheckDates && <p className="muted">{checkHint}</p>}
    </section>
    </div>
    <dialog id="waiting-date-dialog" ref={dateDialog} className="card documents-dialog waiting-date-dialog"
      aria-labelledby="waiting-date-title" onClose={() => setEditingStart(false)}
      onCancel={event => { if (action.busy) event.preventDefault(); }}>
      <div className="section-heading">
        <h2 id="waiting-date-title">Policy start date</h2>
        <button type="button" className="secondary" disabled={action.busy}
          onClick={() => dateDialog.current.close()}>Close</button>
      </div>
      {editingStart && <form onSubmit={event => {
        event.preventDefault();
        const dates = new FormData(event.currentTarget);
        const start = dates.get("coverage");
        action.run(async () => {
          if (!canCheckDates) {
            const saved = await api(`/claims/${id}/policy/start-date`, { coverage_start: start });
            onCoverageStart(saved.coverage_start);
            setResult(null);
            onFinding(null);
          } else {
            const check = await api(`/claims/${id}/policy/waiting-check`, {
              clause, suggestion_id: savedWaiting?.suggestion_id, manual: Boolean(manualWaiting),
              diagnosis, coverage_start: start, admission: admissionDate,
              confirmed: !aiSuggestion || dates.has("confirm-ai"),
            });
            setResult({ ...check, admission: admissionDate });
            onCoverageStart(check.coverage_start);
            onFinding(check.met || check.provisional ? null : check.reason);
          }
          dateDialog.current.close();
        });
      }}>
        {canCheckDates && datedRules.length > 1 && <label>Policy entry<select value={clause}
          onChange={event => setClause(event.target.value)} required>
          <option value="">Choose an entry</option>
          {datedRules.map(rule => <option key={rule.clause} value={rule.clause}>{rule.condition} · {rule.months} months</option>)}
        </select></label>}
        <PolicyStartPicker initialDate={coverageStart} admissionDate={admissionDate} />
        {canCheckDates && aiSuggestion && <label className="check">
          <input type="checkbox" name="confirm-ai" required />
          I checked that the suggested waiting period applies to this diagnosis.
        </label>}
        <div className="diagnosis-editor-actions">
          <button disabled={action.busy}>{action.busy ? "Checking…" : "Check waiting period"}</button>
        </div>
        <ErrorText message={action.error} />
      </form>}
    </dialog>
    {editingWaiting && canLookUp && <form onSubmit={event => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      action.run(async () => {
        const saved = await api(`/claims/${id}/policy/waiting-override`, {
          diagnosis, amount: Number(fields.get("amount")), unit: fields.get("unit"),
        });
        setPolicyEvidence(previous => ({ matches: [], ...previous, waiting_suggestions: [saved] }));
        setEditingWaiting(false);
        setResult(null);
        onFinding(null);
      });
    }}>
      <div className="two-fields">
        <label>Duration<input name="amount" type="number" min="0" max="999" step="1"
          defaultValue={singleWaiting?.amount ?? singleWaiting?.months} required /></label>
        <label>Unit<select name="unit" defaultValue={singleWaiting?.unit || "month"}>
          <option value="day">Days</option><option value="month">Months</option><option value="year">Years</option>
        </select></label>
      </div>
      <button disabled={action.busy}>Save waiting period</button>
      <button type="button" disabled={action.busy} onClick={() => setEditingWaiting(false)}>Cancel</button>
    </form>}
    <ErrorText message={evidenceError} />
    {mismatch && <p className="notice">The discharge summary could not be matched confidently. Check that the hospital documents belong to the same patient and admission.</p>}
    {policyEvidence?.matches.length > 0 && <details>
      <summary>Related policy wording</summary>
      {policyEvidence.matches.map((item, index) => {
        const page = item.citation.match(/PDF page (\d+)/i);
        return <details key={index}><summary>{item.category} · {item.citation}</summary>
          <p>{item.excerpt}</p>
          {page && <PdfPreview claim={id} source={{ document: -1, page: Number(page[1]) }} />}
        </details>;
      })}
    </details>}
    {!editingStart && <ErrorText message={action.error} />}
  </div>;
}

function Estimate({ claim, doc, group, bill, finding, refresh, dirtyBill, sumInsured }) {
  const latest = bill.estimates[0];
  const [revision, setRevision] = useState("");
  const selected = bill.estimates.find(item => item.id === Number(revision)) || latest;
  const [cover, setCover] = useState(latest?.snapshot.remaining_cover ?? sumInsured ?? "");
  const savedCoPay = latest?.snapshot.copayment_rule;
  const originalRate = savedCoPay || bill.copayment_rule;
  const [rate, setRate] = useState(originalRate?.percent ?? "");
  const [rateSource, setRateSource] = useState(originalRate?.excerpt?.replace(/^Customer-reviewed co-payment: /, "") ?? "");
  const [rateEditing, setRateEditing] = useState(false);
  const [rateOverride, setRateOverride] = useState(Boolean(savedCoPay?.excerpt?.startsWith("Customer-reviewed co-payment: ")));
  const [deductions, setDeductions] = useState(() => Object.fromEntries(
    [...bill.suggestions, ...(latest?.snapshot.estimate.deductions || [])].map(item => [item.item.number, item])));
  const rateValid = rate !== "" && Number(rate) >= 0 && Number(rate) <= 100 && Boolean(rateSource.trim());
  const pendingItems = bill.items.filter(item => !Number(deductions[item.number]?.amount) &&
    (bill.expense_evidence[item.number]?.length || /\b(?:consumables|bundle|package)\b/i.test(item.description)));
  const [waitingRow, setWaitingRow] = useState("");
  const action = useAction();
  function edit(row, changes) {
    setDeductions(previous => ({ ...previous, [row]: { ...previous[row], ...changes } }));
  }
  function submit(event) {
    event.preventDefault();
    action.run(async () => {
      await api(`/claims/${claim}/documents/${doc}/estimate`, {
        remaining_cover: cover, confirmed: true, start_page: group,
        reviewed_copayment: !rateOverride && bill.copayment_rule ? null : {
          percent: rate, page: originalRate?.page ?? (bill.copayment_pages.length === 1 ? bill.copayment_pages[0] : null),
          source: rateSource.trim(), confirmed: !rateEditing,
        },
        deductions: Object.entries(deductions).filter(([, value]) => Number(value.amount) !== 0 && value.amount != null)
          .map(([row, value]) => ({ row: Number(row), amount: value.amount, reason: value.reason || "" })),
      });
      setRevision("");
      await refresh();
    });
  }
  const estimate = selected?.snapshot.estimate;
  return <ClaimSection title="Estimate & deductions" className="estimate">
      {estimate && <label className="estimate-revision">Saved estimate<select value={revision} onChange={event => setRevision(event.target.value)}>
        <option value="">Latest revision</option>
        {bill.estimates.map(item => <option key={item.id} value={item.id}>Revision {item.id} · {money(item.snapshot.estimate.payable)}</option>)}
      </select></label>}
    {estimate ? <div className="estimate-overview">
      <div className="estimate-hero"><span>Estimated reimbursement</span><strong>{money(estimate.payable)}</strong></div>
      <dl className="fields estimate-breakdown">
        <dt>Net bill</dt><dd>{money(estimate.net_bill)}</dd>
        {estimate.deductions.map(d => <React.Fragment key={d.item.number}>
          <dt>{d.item.description}<small>Bill page {d.item.page} · {d.reason}</small></dt><dd>−{money(d.amount)}</dd>
        </React.Fragment>)}
        <dt>Remaining-cover adjustment</dt><dd>−{money(estimate.cover_limit_deduction)}</dd>
        <dt>Co-payment ({selected.snapshot.copayment_rule.percent}%)<small>{selected.snapshot.copayment_rule.page && `Policy page ${selected.snapshot.copayment_rule.page} · `}{selected.snapshot.copayment_rule.excerpt}</small></dt>
        <dd>−{money(estimate.copayment)}</dd>
      </dl>
    </div> : <div className="estimate-empty">
      <strong>Estimate not calculated</strong>
      {bill.estimate_ready && <small>Review the remaining cover and deductions below to calculate an estimate.</small>}
    </div>}
    {bill.suggestions.some(item => item.reason?.startsWith("Room and nursing charges above daily limit")) &&
      <p className="notice">Room and nursing charges exceed the policy limit. Review the suggested deduction and any bill discount. Your policy may also reduce other hospital charges proportionately; the estimate does not calculate those reductions automatically.</p>}
    {!bill.estimate_ready ? <div className="notice estimate-blockers">
      <strong>Before calculating an estimate</strong>
      <ul>{bill.estimate_blockers?.map(item => <li key={item}>{item}</li>)}</ul>
    </div> :
      <form className="estimate-form" onSubmit={submit}>
        <div className="estimate-inputs">
          <label>Remaining cover (₹)<input type="number" min="0" step="0.01" required value={cover}
            onChange={event => setCover(event.target.value)} />
            <small>Defaults to the sum insured. Update it if any cover has already been used.</small>
          </label>
        <div className="estimate-copay"><div className="copay-row">
          <div><strong>Co-payment</strong>
            {rate === "" ? <span className="warning-icon" role="img" aria-label="Co-payment needs review"> ⚠</span> : <span> · {rate}%</span>}
            <small>{rateSource || (rate === ""
              ? "No fixed co-payment could be verified. Your policy may let you choose a rate when you buy it; check your policy schedule for the rate and any applicable conditions."
              : "Check your policy schedule and any conditions that apply.")}</small></div>
          <button type="button" className={rateEditing ? "secondary" : "edit-icon"}
            aria-label={rateEditing ? "Use this rate" : "Edit co-payment"} title={rateEditing ? "Use this rate" : "Edit co-payment"}
            disabled={rateEditing && !rateValid}
            onClick={() => { if (rateEditing) setRateOverride(true); setRateEditing(!rateEditing); }}>
            {rateEditing ? "Use this rate" : <span aria-hidden="true">✏︎</span>}</button>
        </div>
        {rateEditing && <div className="copay-editor">
          <label>Co-payment (%)<input type="number" min="0" max="100" step="any" value={rate}
            onChange={event => setRate(event.target.value)} /></label>
          <label>Why this rate applies<textarea value={rateSource} maxLength={1000}
            onChange={event => setRateSource(event.target.value)} /></label>
        {bill.copayment_pages?.length > 0 &&
          <details><summary>Policy references</summary>
            {bill.copayment_pages.map(page => <PdfPreview key={page} claim={claim} source={{ document: -1, page }} />)}
          </details>}
        </div>}
        </div>
        </div>
        {finding && <div className="notice">
          <p>{finding}</p><label>Affected expense<select value={waitingRow} onChange={event => {
            const row = event.target.value;
            setWaitingRow(row);
            if (row) edit(row, { reason: finding });
          }}><option value="">Choose a charge, then enter its amount below</option>
            {bill.items.map(item => <option key={item.number} value={item.number}>{item.description}</option>)}
          </select></label>
        </div>}
        {pendingItems.length > 0 && <details><summary>Needs review ({pendingItems.length})</summary>
          <ul>{pendingItems.map(item => <li key={item.number}><strong>{item.description}</strong> · Bill page {item.page}.
            {/\b(?:consumables|bundle|package)\b/i.test(item.description) ? " Check the itemized bill for separate amounts." :
              " Check which policy wording applies before entering a deduction."}</li>)}</ul>
          <p className="muted">Unresolved charges have no deduction in this estimate. Their coverage has not been verified.</p>
        </details>}
        <div className="estimate-deductions">
        <label>Add a deduction<select value="" onChange={event => {
          if (event.target.value) edit(event.target.value, { amount: "", reason: "" });
        }}>
          <option value="">Choose an expense</option>
          {bill.items.filter(item => !Object.hasOwn(deductions, item.number)).map(item =>
            <option key={item.number} value={item.number}>{item.description}</option>)}
        </select></label>
        {Object.keys(deductions).length ? <details open><summary>Review suggested and added deductions</summary>
          <div className="table-wrap"><table><thead><tr><th>Expense</th><th>Deduct (₹)</th><th>Reason and source</th></tr></thead>
            <tbody>{bill.items.filter(item => Object.hasOwn(deductions, item.number)).map(item => <tr key={item.number}>
              <th>{item.description}<small>{money(item.amount)} · p. {item.page}</small>
                {bill.expense_evidence[item.number]?.map(entry => <small key={entry.citation}>{entry.description} · {entry.citation}</small>)}</th>
              <td><input aria-label={`Deduction for ${item.description}`} type="number" min="0" max={item.amount} step="0.01"
                value={deductions[item.number]?.amount ?? ""} onChange={event => edit(item.number, { amount: event.target.value })} /></td>
              <td><textarea aria-label={`Reason for ${item.description}`} maxLength={1000} value={deductions[item.number]?.reason || ""}
                onChange={event => edit(item.number, { reason: event.target.value })} /></td>
            </tr>)}</tbody>
          </table></div>
        </details> : <p className="muted">No deductions have been added.</p>}
        </div>
        <div className="estimate-submit">
          <label className="check"><input type="checkbox" required /> I reviewed the policy conditions and these deductions.</label>
          <button disabled={action.busy || dirtyBill || rateEditing || !rateValid}>{action.busy ? "Calculating…" : "Calculate estimate"}</button>
        </div>
      </form>}
    <ErrorText message={action.error} />
    <IrdaiReferences />
  </ClaimSection>;
}

function PolicyPicker({ files, onFiles, savedId, onSavedId }) {
  const [policies, setPolicies] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api("/policies").then(result => { if (active) setPolicies(result); })
      .catch(failure => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, []);
  return <>
    {policies.length > 0 && <label>Use a saved policy<select value={savedId} onChange={event => {
      onSavedId(event.target.value);
      if (event.target.value) onFiles([]);
    }}>
      <option value="">Choose a saved policy</option>
      {policies.map(policy => <option key={policy.id} value={policy.id}>
        {policy.name} ({policy.source_claim})
      </option>)}
    </select></label>}
    {!savedId && <Upload label="Choose a new policy PDF" files={files} onFiles={onFiles} />}
    <ErrorText message={error} />
  </>;
}

function SavedWorkspace({ claim, onUpdate }) {
  const [policy, setPolicy] = useState(null);
  const [updatedCoverageStart, setUpdatedCoverageStart] = useState(null);
  const [indexAttempt, setIndexAttempt] = useState(0);
  const [indexError, setIndexError] = useState("");
  const doc = claim.default_bill ?? null;
  const group = claim.default_bill_page ?? null;
  const [clinicalBill, setClinicalBill] = useState(null);
  const [bill, setBill] = useState(null);
  const [finding, setFinding] = useState(null);
  const [dirtyBill, setDirtyBill] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [newPolicy, setNewPolicy] = useState([]);
  const [savedPolicyId, setSavedPolicyId] = useState("");
  const [newBills, setNewBills] = useState([]);
  const action = useAction();
  const documentAction = useAction();
  const documentsDialog = useRef(null);
  const policyDialog = useRef(null);
  const path = `/claims/${claim.id}`;
  useEffect(() => {
    if (!claim.policy) return;
    let show = true;
    setIndexError("");
    async function prepareSearch() {
      const current = await api(path + "/policy");
      if (!show) return;
      setPolicy(current);
      if (current.index_ready || !current.passage_count) return;
      try {
        await api(path + "/policy/index", {});
        const updated = await api(path + "/policy");
        if (!updated.index_ready) throw new Error("Could not prepare policy search.");
        if (show) setPolicy(updated);
      } catch (failure) {
        if (show) setIndexError(failure.message);
      }
    }
    prepareSearch().catch(failure => { if (show) setIndexError(failure.message); });
    return () => { show = false; };
  }, [path, claim.policy, indexAttempt]);
  useEffect(() => {
    setBill(null);
    setFinding(null);
    if (doc == null) return;
    let show = true;
    setLoading(true);
    api(`${path}/documents/${doc}${group ? `?start_page=${group}` : ""}`).then(value => {
      if (show) setBill(value);
    }).catch(failure => { if (show) setError(failure.message); }).finally(() => { if (show) setLoading(false); });
    return () => { show = false; };
  }, [path, doc, group, claim.documents.length, claim.policy]);
  async function refresh() {
    setBill(await api(`${path}/documents/${doc}${group ? `?start_page=${group}` : ""}`));

  }
  const relationships = bill?.relationships;
  const summaries = relationships?.summaries || [];
  const clearMatches = summaries.filter(item => item.clear_match);
  const compatible = summaries.filter(item => !item.differences.length);
  const automatic = clearMatches.length === 1 ? clearMatches[0]
    : clearMatches.length === 0 && compatible.length === 1 ? compatible[0] : null;
  const matched = automatic || (doc == null ? claim.default_summary : null);
  const uncertainSummary = summaries.length > 0 && !matched;
  const matchedIndex = matched?.document ?? null;
  const matchedPage = matched?.page ?? null;
  useEffect(() => {
    setDirtyBill(false);
  }, [doc, group]);
  useEffect(() => {
    setClinicalBill(null);
    setFinding(null);
    if (matchedIndex == null) return;
    let active = true;
    api(`${path}/documents/${matchedIndex}?summary_page=${matchedPage}`).then(value => { if (active) setClinicalBill(value); })
      .catch(failure => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [path, matchedIndex, matchedPage, doc, group]);
  const matchedBill = clinicalBill;
  const searchState = policy?.index_ready ? "ready"
    : !claim.policy || indexError || policy?.passage_count === 0 ? "not-ready" : "preparing";
  const searchLabel = { ready: "Ready", preparing: "Preparing", "not-ready": "Not ready" }[searchState];
  const detailsBill = matchedBill || bill;
  const patientFields = Object.values(detailsBill?.fields || {});
  const patientNames = [...new Map(patientFields.flatMap(fields => {
    const name = fields["Patient name"];
    return name?.text ? [[name.normalized || name.text, name.text]] : [];
  })).values()];
  const patientName = relationships?.conflicts.length || patientNames.length > 1
    ? "Needs review"
    : patientNames[0] || (loading ? "Reading document…" : "Name not available");
  const documentTypes = claim.document_types || [];
  const hasSummary = documentTypes.some(types => types.includes("Discharge Summary")) || summaries.length > 0;
  const missingDocuments = [];
  if (doc == null) missingDocuments.push("No hospital bill identified. Add the final bill to review charges.");
  if (!hasSummary) missingDocuments.push("No discharge summary identified. Add it to help verify the diagnosis and admission dates.");
  if (bill && !bill.items.length) missingDocuments.push("No itemized charges found. Add a bill that lists the individual charges.");
  function attach(event, files, field) {
    event.preventDefault();
    const uploadAction = field === "documents" ? documentAction : action;
    uploadAction.run(async () => {
      const body = new FormData();
      files.forEach(file => body.append(field, file));
      if (field === "policy" && savedPolicyId) body.set("saved_policy_id", savedPolicyId);
      const updated = await api(path + "/documents", body);
      if (field === "documents") setNewBills([]);
      else setNewPolicy([]);
      onUpdate(updated);
    });
  }
  return <>
    <ErrorText message={error} />
    {relationships?.conflicts.length > 0 && <div className="notice" role="alert">
      <strong>These bills list different patients.</strong> Use a separate claim for the other patient before estimating.
      <ul>{relationships.conflicts.map(message => <li key={message}>{message}</li>)}</ul>
    </div>}
    {relationships?.warnings.map(message => <p className="notice" key={message}>{message}</p>)}
    <div className="claim-tiles">
      <section className="card claim-tile patient-tile">
        <span className="tile-icon person-icon" aria-hidden="true" />
        <h2>Patient name</h2>
        <p className="tile-value">{patientName}</p>
      </section>
      <button type="button" className={`card claim-tile interactive-tile insurance-tile policy-${searchState}`}
        aria-haspopup="dialog" onClick={() => policyDialog.current.showModal()}>
        <span className="tile-header">
          <span className="tile-icon file-icon" aria-hidden="true" />
          <span className="tile-open" aria-hidden="true">↗</span>
        </span>
        <span className="tile-label">Insurance policy</span>
        <span className="tile-value">{claim.policy || "No policy attached"}</span>
        <span className="policy-status" role="status" aria-label={`Policy search ${searchLabel.toLowerCase()}`}>{searchLabel}</span>
      </button>
      <button type="button" className="card claim-tile interactive-tile hospital-tile" aria-haspopup="dialog"
        onClick={() => documentsDialog.current.showModal()}>
        <span className="tile-header">
          <span className="tile-icon file-icon stack-icon" aria-hidden="true" />
          <span className="tile-open" aria-hidden="true">↗</span>
        </span>
        <span className="tile-label">Hospital documents</span>
        <span className="tile-number">{claim.documents.length}</span>
      </button>
      <section className="card claim-tile total-tile">
        <span className="tile-icon" aria-hidden="true">₹</span>
        <h2>Net hospital bill</h2>
        <p className="tile-number">{money(bill?.totals?.net?.amount)}</p>
        {bill?.totals?.net?.amount == null && <small>{loading ? "Reading bill…" : "No bill total available"}</small>}
      </section>
    </div>
    <dialog ref={policyDialog} className="card documents-dialog" aria-labelledby="policy-dialog-title">
      <div className="section-heading">
        <h2 id="policy-dialog-title">Insurance policy</h2>
        <button type="button" className="secondary" onClick={() => policyDialog.current.close()}>Close</button>
      </div>
      {claim.policy ? <>
        <div className="policy-file-row">
          <div>
            <p className="tile-value">{claim.policy}</p>
            {policy && <p className="file-meta">{policy.page_count} PDF {policy.page_count === 1 ? "page" : "pages"}</p>}
          </div>
          <a className="download-button" href={`/api${path}/policy/download`} download
            aria-label="Download policy PDF" title="Download policy PDF"><span aria-hidden="true">⬇︎</span></a>
        </div>
        {indexError && <>
          <ErrorText message={indexError} />
          <button type="button" className="secondary" onClick={() => setIndexAttempt(attempt => attempt + 1)}>Retry</button>
        </>}
        {policy && <>
          <PolicyLimitCheck observations={policy.waiting_limit_evidence || []} />
          {policy.room_limit && <details><summary>Room limit</summary>
            <p>{policy.room_limit.excerpt}</p>
            <PdfPreview claim={claim.id} source={{ document: -1, page: policy.room_limit.page }} />
          </details>}
        </>}
      </> : <form onSubmit={event => attach(event, newPolicy, "policy")}>
        <PolicyPicker files={newPolicy} onFiles={setNewPolicy} savedId={savedPolicyId} onSavedId={setSavedPolicyId} />
        <button disabled={action.busy || (!newPolicy.length && !savedPolicyId)}>Attach policy</button>
      </form>}
      <ErrorText message={action.error} />
    </dialog>
    <dialog ref={documentsDialog} className="card documents-dialog" aria-labelledby="documents-dialog-title">
      <div className="section-heading">
        <h2 id="documents-dialog-title">Hospital documents</h2>
        <button type="button" className="secondary" onClick={() => documentsDialog.current.close()}>Close</button>
      </div>
      {claim.documents.length ? <ul className="document-list">
        {claim.documents.map((name, index) => <li key={index}>
          <span>{name}</span>
          <small>{[...(documentTypes[index] || []), ...(index === doc ? ["Used for bill review"] : [])].join(" · ") || "Document type not identified"}</small>
        </li>)}
      </ul> : <p className="muted">No hospital PDFs uploaded yet.</p>}
      {missingDocuments.length > 0 && <section className="document-suggestions">
        <h3>Suggested documents</h3>
        <ul>{missingDocuments.map(message => <li key={message}>{message}</li>)}</ul>
      </section>}
      <form onSubmit={event => attach(event, newBills, "documents")}>
        <Upload label="Choose hospital PDFs" files={newBills} onFiles={setNewBills} multiple />
        <button disabled={documentAction.busy || dirtyBill || !newBills.length}>
          {documentAction.busy ? "Uploading…" : "Upload documents"}
        </button>
        <ErrorText message={documentAction.error} />
      </form>
    </dialog>
    <Chat key={`${claim.id}:${doc}:${group}`} id={claim.id} hasPolicy={Boolean(claim.policy)} doc={doc} group={group}
      ready={policy?.index_ready ?? false} summary={matched} />
    {detailsBill ? <div className="support-grid">
      <ClaimDetails key={`details:${doc}:${group}:${matchedIndex}:${matchedPage}:${Boolean(matchedBill)}`}
        claim={claim.id} document={matchedBill ? matchedIndex : doc}
        summaryPage={matchedBill ? matchedPage : null} bill={detailsBill} onDiagnosisChange={() => setFinding(null)}>
        {(diagnosis, procedure) => <WaitingReview key={diagnosis} id={claim.id} bill={detailsBill}
            diagnosis={diagnosis} procedure={procedure} policy={policy} onFinding={setFinding}
            coverageStart={updatedCoverageStart || policy?.coverage_start} onCoverageStart={setUpdatedCoverageStart}
            mismatch={Boolean(relationships?.conflicts.length || uncertainSummary)} />}
      </ClaimDetails>
      {bill && <>
        <BillReview key={`review:${doc}:${group}`} claim={claim.id} doc={doc} group={group}
          bill={bill} refresh={refresh} onDirty={setDirtyBill} />
        <Estimate key={`estimate:${doc}:${group}:${bill.identity}`} claim={claim.id} doc={doc} group={group} bill={bill}
          sumInsured={claim.sum_insured} finding={finding} refresh={refresh} dirtyBill={dirtyBill} />
      </>}
    </div> : <ClaimSection title="Extracted claim details" className="claim-details" initiallyOpen>
      <p className="muted">{loading || (matchedIndex != null && !error) ? "Reading hospital documents…" : doc == null && matchedIndex == null
        ? "Upload a hospital bill or discharge summary to see the extracted details."
        : "Claim details could not be loaded."}</p>
      <WaitingReview id={claim.id} bill={null} diagnosis="" procedure="" policy={policy} onFinding={setFinding}
        coverageStart={updatedCoverageStart || policy?.coverage_start} onCoverageStart={setUpdatedCoverageStart}
        mismatch={false} />
    </ClaimSection>}
  </>;
}

function NewClaim({ onSave }) {
  const [policy, setPolicy] = useState([]);
  const [savedPolicyId, setSavedPolicyId] = useState("");
  const [bills, setBills] = useState([]);
  const action = useAction();
  function submit(event) {
    event.preventDefault();
    const payload = new FormData(event.currentTarget);
    if (!payload.get("sum_insured")) payload.delete("sum_insured");
    if (policy[0]) payload.set("policy", policy[0]);
    if (savedPolicyId) payload.set("saved_policy_id", savedPolicyId);
    bills.forEach(file => payload.append("documents", file));
    action.run(async () => onSave(await api("/claims", payload)));
  }
  return <>
    <form onSubmit={submit}>
      <section className="card claim-form">
        <label>Claim name<input name="name" maxLength={120} required placeholder="For example, November hospital visit" /></label>
        <label>Sum insured (₹)<input type="number" min={1} step={1} name="sum_insured" placeholder="Optional" /></label>
      </section>
      <div className="primary-grid new-documents">
        <section className="card document-card"><h2>Insurance policy</h2>
          <PolicyPicker files={policy} onFiles={setPolicy} savedId={savedPolicyId} onSavedId={setSavedPolicyId} />
        </section>
        <section className="card document-card hospital-upload-card">
          <h2>Hospital documents</h2>
          <Upload label="Choose hospital PDFs" files={bills} onFiles={setBills} multiple />
        </section>
      </div>
      <div className="claim-submit">
        <button disabled={action.busy || (!policy.length && !savedPolicyId && !bills.length)}>{action.busy ? "Saving…" : "Save claim"}</button>
        <ErrorText message={action.error} />
      </div>
    </form>
  </>;
}

function Workspace({ onLogout, themeToggle }) {
  const [list, setList] = useState([]);
  const [claim, setClaim] = useState(null);
  const action = useAction();
  const deleteDialog = useRef(null);
  const claimPicker = useRef(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteNotice, setDeleteNotice] = useState("");
  useEffect(() => { action.run(async () => setList(await api("/claims"))); }, []);
  useEffect(() => {
    const closePicker = event => {
      if (claimPicker.current && !claimPicker.current.contains(event.target)) claimPicker.current.open = false;
    };
    document.addEventListener("pointerdown", closePicker);
    return () => document.removeEventListener("pointerdown", closePicker);
  }, []);
  return <>
    <header className="topbar"><Brand /><div className="topbar-actions">{themeToggle}<button className="secondary" onClick={() => action.run(async () => {
      await api("/logout", {}); onLogout();
    })}>Sign out</button></div></header>
    <main className="workspace">
      <div className="workspace-heading">
        <div className="workspace-title">
          <h1>{claim?.name || "New claim"}</h1>
          {claim ? claim.sum_insured && <span>Sum insured {money(claim.sum_insured)}</span>
            : <span>Keep each patient’s hospital documents in a separate claim.</span>}
        </div>
        <nav className="claim-nav" aria-label="Saved claims">
          {claim && <button type="button" className="secondary" disabled={action.busy} onClick={() => setClaim(null)}>New claim</button>}
          <div className="claim-picker">
            <span className="claim-picker-label" id="saved-claims-label">Saved claims</span>
            <details ref={claimPicker} className="claim-picker-dropdown" onKeyDown={event => {
              if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); }
            }}>
              <summary aria-labelledby="saved-claims-label saved-claims-value">
                <span id="saved-claims-value">{claim?.name || "New claim"}</span>
                <span aria-hidden="true" className="claim-picker-chevron">&#8964;</span>
              </summary>
              <div className="claim-picker-list" aria-label="Choose or delete a saved claim">
                <button type="button" className="claim-picker-choice" disabled={action.busy} onClick={() => {
                  claimPicker.current.open = false; setClaim(null);
                }}>New claim</button>
                {list.map(item => <div className="claim-picker-row" key={item.id}>
                  <button type="button" className="claim-picker-choice" disabled={action.busy}
                    aria-current={claim?.id === item.id ? "true" : undefined} onClick={() => {
                      claimPicker.current.open = false;
                      action.run(async () => setClaim(await api(`/claims/${item.id}`)));
                    }}>{item.name}</button>
                  <button type="button" className="claim-picker-delete" disabled={action.busy}
                    aria-label={`Delete ${item.name}`} title={`Delete ${item.name}`} onClick={() => {
                      claimPicker.current.open = false; action.clearError(); setDeleteTarget(item);
                      deleteDialog.current.showModal();
                    }}>&#215;</button>
                </div>)}
              </div>
            </details>
          </div>
        </nav>
      </div>
      <ErrorText message={action.error} />
      {deleteNotice && <p className="notice" role="status">{deleteNotice}</p>}
      <dialog ref={deleteDialog} className="card documents-dialog" aria-labelledby="delete-claim-title">
        <h2 id="delete-claim-title">Delete claim?</h2>
        <p>Delete {deleteTarget?.name}? Its chat and saved estimates will also be deleted. Documents shared with another claim will remain available there.</p>
        <div className="actions">
          <button type="button" className="secondary" disabled={action.busy} onClick={() => deleteDialog.current.close()}>Cancel</button>
          <button type="button" disabled={action.busy} onClick={() => action.run(async () => {
            const id = deleteTarget.id;
            const result = await api(`/claims/${id}`, null, "DELETE");
            deleteDialog.current.close();
            setList(current => current.filter(item => item.id !== id));
            setClaim(current => current?.id === id ? null : current);
            setDeleteTarget(null);
            setDeleteNotice(result.file_cleanup_pending
              ? "Claim deleted, but some document files could not be removed from this device."
              : "Claim deleted.");
          })}>{action.busy ? "Deleting..." : "Delete claim"}</button>
        </div>
        <ErrorText message={action.error} />
      </dialog>
      {claim ? <SavedWorkspace key={claim.id} claim={claim} onUpdate={setClaim} /> :
        <NewClaim onSave={saved => { setList(current => [{ id: saved.id, name: saved.name }, ...current]); setClaim(saved); }} />}
    </main>
  </>;
}

function App() {
  const [signedIn, setSignedIn] = useState(null);
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem("claims-theme");
      if (saved === "dark" || saved === "light") return saved === "dark";
    } catch { /* Follow the device preference when storage is unavailable. */ }
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [dark]);
  const themeToggle = <button type="button" className="secondary theme-toggle" aria-pressed={dark} onClick={() => {
    const next = !dark;
    setDark(next);
    try { localStorage.setItem("claims-theme", next ? "dark" : "light"); }
    catch { /* The current tab still uses the selected theme. */ }
  }}><span aria-hidden="true">{dark ? "☀︎" : "☾"}</span> Dark mode</button>;
  useEffect(() => { api("/session").then(() => setSignedIn(true)).catch(() => setSignedIn(false)); }, []);
  if (signedIn === null) return <main className="workspace"><p role="status">Opening Claims Assist…</p></main>;
  return signedIn ? <Workspace onLogout={() => setSignedIn(false)} themeToggle={themeToggle} />
    : <SignIn onLogin={() => setSignedIn(true)} themeToggle={themeToggle} />;
}

createRoot(document.getElementById("root")).render(<App />);
