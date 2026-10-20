import { useEffect, useState } from "react";
import {
  api,
  initAuthToken,
  setAuthToken,
  clearAuthToken,
} from "./api";
import type {
  SubscriptionInfo,
  RunItem,
  RunResultResponse,
} from "./api";
import { VALID_FIXTURE, INVALID_FIXTURE } from "./fixtures";

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [activeTab, setActiveTab] = useState<"tools" | "history">("tools");

  // Subscription state
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [_subLoading, setSubLoading] = useState(false);
  const [subError, setSubError] = useState<string | null>(null);

  // Run tools state
  const [operation, setOperation] = useState<"validate" | "process">("validate");
  const [recordsJson, setRecordsJson] = useState<string>(
    JSON.stringify(VALID_FIXTURE, null, 2)
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<{
    status: number;
    data: any;
    idempotencyKey?: string;
  } | null>(null);

  // History state
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunResult, setSelectedRunResult] = useState<RunResultResponse | null>(null);
  const [resultLoading, setResultLoading] = useState(false);

  // Initialize token from URL or session
  useEffect(() => {
    const t = initAuthToken();
    if (t) {
      setToken(t);
    }
  }, []);

  // Fetch subscription data when token changes
  useEffect(() => {
    if (token) {
      loadSubscription();
    } else {
      setSubscription(null);
    }
  }, [token]);

  // Fetch runs when switching to History tab
  useEffect(() => {
    if (token && activeTab === "history") {
      loadRuns();
    }
  }, [token, activeTab]);

  const loadSubscription = async () => {
    setSubLoading(true);
    setSubError(null);
    try {
      const res = await api.getSubscription();
      if (res.status === 200 && res.data) {
        setSubscription(res.data);
        // If Basic, ensure operation is validate
        if (res.data.plan === "Basic" && operation === "process") {
          setOperation("validate");
        }
      } else {
        setSubError((res.data as any)?.error?.message || "Failed to load subscription.");
      }
    } catch (e: any) {
      setSubError(e.message || "Network error loading subscription.");
    } finally {
      setSubLoading(false);
    }
  };

  const loadRuns = async () => {
    setRunsLoading(true);
    try {
      const res = await api.getRuns();
      if (res.status === 200 && res.data && res.data.runs) {
        setRuns(res.data.runs);
      }
    } catch (e) {
      console.error("Error loading runs:", e);
    } finally {
      setRunsLoading(false);
    }
  };

  const selectRun = async (runId: string) => {
    setSelectedRunId(runId);
    setResultLoading(true);
    setSelectedRunResult(null);
    try {
      const res = await api.getRunResult(runId);
      if (res.status === 200 && res.data) {
        setSelectedRunResult(res.data);
      }
    } catch (e) {
      console.error("Error loading run result:", e);
    } finally {
      setResultLoading(false);
    }
  };

  const handleApplyToken = () => {
    if (tokenInput.trim()) {
      setAuthToken(tokenInput.trim());
      setToken(tokenInput.trim());
      setTokenInput("");
    }
  };

  const handleClearAuth = () => {
    clearAuthToken();
    setToken(null);
    setSubscription(null);
    setSubmitResult(null);
    setRuns([]);
    setSelectedRunId(null);
  };

  const handleSubmitRun = async () => {
    setSubmitting(true);
    setSubmitResult(null);

    let parsedRecords: any[];
    try {
      parsedRecords = JSON.parse(recordsJson);
      if (!Array.isArray(parsedRecords)) {
        throw new Error("Records must be a JSON array of objects.");
      }
    } catch (err: any) {
      setSubmitting(false);
      setSubmitResult({
        status: 400,
        data: { error: { code: "INVALID_JSON", message: err.message || "Invalid JSON array." } },
      });
      return;
    }

    // Generate fresh idempotency key
    const idempotencyKey = "run-" + crypto.randomUUID();

    try {
      const res = await api.createRun(operation, parsedRecords, idempotencyKey);
      setSubmitResult({
        status: res.status,
        data: res.data,
        idempotencyKey,
      });
      // Refresh subscription to update quota
      loadSubscription();
    } catch (err: any) {
      setSubmitResult({
        status: 500,
        data: { error: { code: "NETWORK_ERROR", message: err.message || "Request failed." } },
        idempotencyKey,
      });
    } finally {
      setSubmitting(false);
    }
  };

  // Quota bar calculations
  const used = subscription?.used_quota || 0;
  const total = subscription?.daily_quota || 1;
  const remaining = subscription?.remaining_quota || 0;
  const quotaPct = Math.min(100, Math.round((used / total) * 100));

  return (
    <div className="container">
      {/* App Header */}
      <header className="app-header">
        <div className="brand">
          <h1>Customer Data Quality SaaS</h1>
          <span className="brand-badge">UC-01</span>
        </div>

        {/* Tenant context and quota indicators */}
        {subscription && (
          <div className="tenant-bar">
            <div>
              <span className={`chip chip-${subscription.plan.toLowerCase()}`}>
                {subscription.plan} Plan
              </span>
            </div>
            <div>
              <span
                className={`chip ${
                  subscription.status === "Active" ? "chip-active" : "chip-suspended"
                }`}
              >
                ● {subscription.status}
              </span>
            </div>
            <div className="quota-wrapper">
              <div className="quota-label">
                <span>Daily Quota</span>
                <span>
                  {used}/{total} ({remaining} left)
                </span>
              </div>
              <div className="quota-bar-bg">
                <div
                  className={`quota-bar-fill ${
                    remaining === 0 ? "exhausted" : quotaPct > 75 ? "warning" : ""
                  }`}
                  style={{ width: `${quotaPct}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {token && (
          <button className="btn btn-secondary" onClick={handleClearAuth} title="Disconnect session">
            Log out
          </button>
        )}
      </header>

      {/* Authentication Banner if missing token */}
      {subError && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          <strong>Subscription Notice:</strong> {subError}
        </div>
      )}

      {!token && (
        <div className="card">
          <h2 className="card-title">Authentication Required</h2>
          <p style={{ color: "var(--text-muted)", marginBottom: 16 }}>
            Please authenticate using a bearer session token. You can pass <code>?token=...</code> in the
            URL or paste a minted token below:
          </p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder="Paste JWT Token..."
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              style={{
                flex: "1 1 300px",
                padding: "8px 12px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border)",
                background: "var(--bg-input)",
                color: "#fff",
              }}
            />
            <button className="btn btn-primary" onClick={handleApplyToken}>
              Set Token
            </button>
          </div>
        </div>
      )}

      {token && (
        <>
          {/* Navigation Tabs */}
          <nav className="tabs" role="tablist">
            <button
              className={`tab-btn ${activeTab === "tools" ? "active" : ""}`}
              onClick={() => setActiveTab("tools")}
              role="tab"
              aria-selected={activeTab === "tools"}
            >
              Run Tools
            </button>
            <button
              className={`tab-btn ${activeTab === "history" ? "active" : ""}`}
              onClick={() => setActiveTab("history")}
              role="tab"
              aria-selected={activeTab === "history"}
            >
              History
            </button>
          </nav>

          {/* TAB 1: RUN TOOLS */}
          {activeTab === "tools" && (
            <div>
              <div className="card">
                <h2 className="card-title">Configure & Submit Batch</h2>

                {/* Operation selector */}
                <div className="form-group">
                  <span className="form-label">Select Operation</span>
                  <div className="radio-group">
                    <label className="radio-label">
                      <input
                        type="radio"
                        name="operation"
                        value="validate"
                        checked={operation === "validate"}
                        onChange={() => setOperation("validate")}
                      />
                      <span>Validate (Rules R1 - R4)</span>
                    </label>

                    <label
                      className={`radio-label ${
                        subscription?.plan === "Basic" ? "disabled" : ""
                      }`}
                      title={
                        subscription?.plan === "Basic"
                          ? "Process operation requires Pro plan"
                          : ""
                      }
                    >
                      <input
                        type="radio"
                        name="operation"
                        value="process"
                        disabled={subscription?.plan === "Basic"}
                        checked={operation === "process"}
                        onChange={() => setOperation("process")}
                      />
                      <span>
                        Process (Standardise & Contactable Report){" "}
                        {subscription?.plan === "Basic" && (
                          <small style={{ color: "var(--text-dim)" }}>(Pro only)</small>
                        )}
                      </span>
                    </label>
                  </div>
                </div>

                {/* Fixture buttons */}
                <div className="form-group">
                  <span className="form-label">Customer Batch Records (1 to 10 rows JSON)</span>
                  <div className="btn-group" style={{ marginBottom: 8 }}>
                    <button
                      className="btn btn-secondary"
                      type="button"
                      onClick={() => setRecordsJson(JSON.stringify(VALID_FIXTURE, null, 2))}
                    >
                      Load Valid Fixture
                    </button>
                    <button
                      className="btn btn-secondary"
                      type="button"
                      onClick={() => setRecordsJson(JSON.stringify(INVALID_FIXTURE, null, 2))}
                    >
                      Load Invalid Fixture
                    </button>
                    <button
                      className="btn btn-secondary"
                      type="button"
                      onClick={() => setRecordsJson("[]")}
                    >
                      Clear
                    </button>
                  </div>

                  <textarea
                    className="input-code"
                    value={recordsJson}
                    onChange={(e) => setRecordsJson(e.target.value)}
                    rows={10}
                    placeholder="[ { 'record_id': 'C01', 'email': 'alice@example.com', 'credit_limit': 500, 'status': 'ACTIVE' } ]"
                  />
                </div>

                <div className="btn-group">
                  <button
                    className="btn btn-primary"
                    disabled={submitting || subscription?.status === "Suspended"}
                    onClick={handleSubmitRun}
                  >
                    {submitting ? "Submitting..." : "Submit Run"}
                  </button>
                </div>
              </div>

              {/* Result display */}
              {submitResult && (
                <div className="card">
                  <h3 className="card-title">
                    <span>Submission Response</span>
                    <span
                      className={`status-badge ${
                        submitResult.status === 201
                          ? submitResult.data?.status === "Failed"
                            ? "failed"
                            : "succeeded"
                          : submitResult.status === 200
                          ? "succeeded"
                          : "failed"
                      }`}
                    >
                      HTTP {submitResult.status}{" "}
                      {submitResult.status === 200 && "(Idempotent Replay)"}
                    </span>
                  </h3>

                  {submitResult.idempotencyKey && (
                    <p style={{ fontSize: "0.8rem", color: "var(--text-dim)", marginBottom: 12 }}>
                      Idempotency-Key: <code>{submitResult.idempotencyKey}</code>
                    </p>
                  )}

                  {/* 4xx / 5xx error box */}
                  {submitResult.status >= 400 && (
                    <div className="alert alert-error">
                      <strong>
                        {submitResult.status === 429
                          ? "429 Quota Exhausted"
                          : submitResult.status === 403
                          ? "403 Forbidden"
                          : submitResult.status === 409
                          ? "409 Conflict"
                          : "Error"}
                        : {submitResult.data?.error?.code || "REQUEST_FAILED"}
                      </strong>
                      <p>{submitResult.data?.error?.message || JSON.stringify(submitResult.data)}</p>
                    </div>
                  )}

                  {/* 201 or 200 Success / Run details */}
                  {(submitResult.status === 201 || submitResult.status === 200) && (
                    <div>
                      {submitResult.data?.run_id && (
                        <p style={{ fontSize: "0.85rem", marginBottom: 12 }}>
                          Run ID: <code>{submitResult.data.run_id}</code> | Status:{" "}
                          <strong>{submitResult.data.status}</strong>
                        </p>
                      )}

                      {/* Forced or execution failure */}
                      {submitResult.data?.status === "Failed" && (
                        <div className="alert alert-error">
                          <strong>Run Failed</strong>
                          <p>
                            Code: {submitResult.data.error?.code || "UNKNOWN"} <br />
                            Message: {submitResult.data.error?.message}
                          </p>
                        </div>
                      )}

                      {/* Validation Result */}
                      {submitResult.data?.result?.valid_rows !== undefined && (
                        <div>
                          <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
                            <span className="chip chip-active">
                              Valid Rows: {submitResult.data.result.valid_rows}
                            </span>
                            <span
                              className={`chip ${
                                submitResult.data.result.invalid_rows > 0
                                  ? "chip-suspended"
                                  : "chip-active"
                              }`}
                            >
                              Invalid Rows: {submitResult.data.result.invalid_rows}
                            </span>
                          </div>

                          {submitResult.data.result.issues?.length > 0 ? (
                            <div className="table-wrapper">
                              <table>
                                <thead>
                                  <tr>
                                    <th>Row Index</th>
                                    <th>Field</th>
                                    <th>Rule ID</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {submitResult.data.result.issues.map(
                                    (iss: any, idx: number) => (
                                      <tr key={idx}>
                                        <td>{iss.row_index}</td>
                                        <td>{iss.field}</td>
                                        <td>
                                          <span className="brand-badge">{iss.rule_id}</span>
                                        </td>
                                      </tr>
                                    )
                                  )}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <div className="alert alert-success">
                              All rows validated successfully!
                            </div>
                          )}
                        </div>
                      )}

                      {/* Process Result */}
                      {submitResult.data?.result?.summary && (
                        <div>
                          <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
                            <span className="chip chip-basic">
                              Input Rows: {submitResult.data.result.summary.input_rows}
                            </span>
                            <span className="chip chip-pro">
                              Contactable Rows:{" "}
                              {submitResult.data.result.summary.contactable_rows}
                            </span>
                          </div>

                          <div className="table-wrapper">
                            <table>
                              <thead>
                                <tr>
                                  <th>Record ID</th>
                                  <th>Standardised Email</th>
                                  <th>Contactable</th>
                                </tr>
                              </thead>
                              <tbody>
                                {submitResult.data.result.rows?.map(
                                  (r: any, idx: number) => (
                                    <tr key={idx}>
                                      <td>{r.record_id}</td>
                                      <td>{r.email}</td>
                                      <td>
                                        <span
                                          className={`status-badge ${
                                            r.contactable ? "succeeded" : "failed"
                                          }`}
                                        >
                                          {r.contactable ? "True" : "False"}
                                        </span>
                                      </td>
                                    </tr>
                                  )
                                )}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: HISTORY */}
          {activeTab === "history" && (
            <div>
              <div className="card">
                <div className="card-title">
                  <span>Tenant Run History</span>
                  <button className="btn btn-secondary" onClick={loadRuns} disabled={runsLoading}>
                    {runsLoading ? "Refreshing..." : "Refresh"}
                  </button>
                </div>

                {runs.length === 0 ? (
                  <p style={{ color: "var(--text-muted)", padding: "16px 0" }}>
                    No runs recorded yet for this tenant.
                  </p>
                ) : (
                  <div className="table-wrapper">
                    <table>
                      <thead>
                        <tr>
                          <th>Run ID</th>
                          <th>Operation</th>
                          <th>Status</th>
                          <th>Idempotency Key</th>
                          <th>Created At</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runs.map((r) => (
                          <tr
                            key={r.run_id}
                            className={`clickable ${
                              selectedRunId === r.run_id ? "selected" : ""
                            }`}
                            onClick={() => selectRun(r.run_id)}
                          >
                            <td>
                              <code>{r.run_id.slice(0, 8)}...</code>
                            </td>
                            <td>{r.operation}</td>
                            <td>
                              <span
                                className={`status-badge ${
                                  r.status === "Succeeded"
                                    ? "succeeded"
                                    : r.status === "Failed"
                                    ? "failed"
                                    : "running"
                                }`}
                              >
                                {r.status}
                              </span>
                            </td>
                            <td>
                              <small>{r.idempotency_key}</small>
                            </td>
                            <td>{new Date(r.created_at).toLocaleTimeString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Selected Run Result View */}
              {selectedRunId && (
                <div className="card">
                  <h3 className="card-title">
                    <span>Run Details</span>
                    <code>{selectedRunId}</code>
                  </h3>

                  {resultLoading && <p style={{ color: "var(--text-muted)" }}>Loading result...</p>}

                  {selectedRunResult && (
                    <div>
                      <p style={{ marginBottom: 12 }}>
                        Status:{" "}
                        <span
                          className={`status-badge ${
                            selectedRunResult.status === "Succeeded"
                              ? "succeeded"
                              : selectedRunResult.status === "Failed"
                              ? "failed"
                              : "running"
                          }`}
                        >
                          {selectedRunResult.status}
                        </span>
                      </p>

                      {selectedRunResult.status === "Failed" && (
                        <div className="alert alert-error">
                          <strong>Recorded Error</strong>
                          <p>
                            Code: {selectedRunResult.error?.code || "UNKNOWN"} <br />
                            Message: {selectedRunResult.error?.message}
                          </p>
                        </div>
                      )}

                      {/* Succeeded validate */}
                      {(selectedRunResult.result as any)?.valid_rows !== undefined && (
                        <div>
                          <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
                            <span className="chip chip-active">
                              Valid Rows: {(selectedRunResult.result as any).valid_rows}
                            </span>
                            <span
                              className={`chip ${
                                (selectedRunResult.result as any).invalid_rows > 0
                                  ? "chip-suspended"
                                  : "chip-active"
                              }`}
                            >
                              Invalid Rows: {(selectedRunResult.result as any).invalid_rows}
                            </span>
                          </div>

                          {(selectedRunResult.result as any).issues?.length > 0 ? (
                            <div className="table-wrapper">
                              <table>
                                <thead>
                                  <tr>
                                    <th>Row Index</th>
                                    <th>Field</th>
                                    <th>Rule ID</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(selectedRunResult.result as any).issues.map(
                                    (iss: any, idx: number) => (
                                      <tr key={idx}>
                                        <td>{iss.row_index}</td>
                                        <td>{iss.field}</td>
                                        <td>
                                          <span className="brand-badge">{iss.rule_id}</span>
                                        </td>
                                      </tr>
                                    )
                                  )}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <div className="alert alert-success">
                              All rows in this run were valid.
                            </div>
                          )}
                        </div>
                      )}

                      {/* Succeeded process */}
                      {(selectedRunResult.result as any)?.summary && (
                        <div>
                          <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
                            <span className="chip chip-basic">
                              Input Rows: {(selectedRunResult.result as any).summary.input_rows}
                            </span>
                            <span className="chip chip-pro">
                              Contactable Rows:{" "}
                              {(selectedRunResult.result as any).summary.contactable_rows}
                            </span>
                          </div>

                          <div className="table-wrapper">
                            <table>
                              <thead>
                                <tr>
                                  <th>Record ID</th>
                                  <th>Standardised Email</th>
                                  <th>Contactable</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(selectedRunResult.result as any).rows?.map(
                                  (r: any, idx: number) => (
                                    <tr key={idx}>
                                      <td>{r.record_id}</td>
                                      <td>{r.email}</td>
                                      <td>
                                        <span
                                          className={`status-badge ${
                                            r.contactable ? "succeeded" : "failed"
                                          }`}
                                        >
                                          {r.contactable ? "True" : "False"}
                                        </span>
                                      </td>
                                    </tr>
                                  )
                                )}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
