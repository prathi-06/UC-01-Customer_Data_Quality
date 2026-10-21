import { useEffect, useState } from "react";
import {
  api,
  getAuthToken,
  setAuthToken,
  clearAuthToken,
  checkAndConsumeUrlToken,
  parseTokenClaims,
  getRememberedAccounts,
  saveRememberedAccount,
  setOnUnauthorized,
} from "./api";
import type {
  SubscriptionInfo,
  RunItem,
  RunResultResponse,
  RememberedAccount,
} from "./api";
import { VALID_FIXTURE, INVALID_FIXTURE } from "./fixtures";

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [activeTab, setActiveTab] = useState<"tools" | "history">("tools");

  // Sign-in state
  const [validating, setValidating] = useState(false);
  const [signInError, setSignInError] = useState<string | null>(null);
  const [rememberedAccounts, setRememberedAccounts] = useState<RememberedAccount[]>([]);

  // User identity state from token & /subscription
  const [currentUser, setCurrentUser] = useState<string>("");
  const [currentRole, setCurrentRole] = useState<string>("");

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

  // Authenticate token candidate against /subscription
  const validateAndSignIn = async (candidateToken: string, autoSwitch: boolean = false) => {
    const trimmed = candidateToken.trim();
    if (!trimmed) {
      setSignInError("Token not accepted");
      return;
    }

    setValidating(true);
    setSignInError(null);
    setSubError(null);

    // Save token in sessionStorage & memory
    setAuthToken(trimmed);

    try {
      const res = await api.getSubscription();
      if (res.status === 200 && res.data) {
        const claims = parseTokenClaims(trimmed);
        const user = (res.data as any)?.user || claims?.user || "Tester";
        const role = (res.data as any)?.role || claims?.role || "Tester";
        const tenantName = res.data.name || (res.data as any)?.tenant_name || res.data.tenant_id;

        const label = `${user}, ${tenantName}, ${role}`;
        const account: RememberedAccount = {
          token: trimmed,
          user,
          tenant: tenantName,
          role,
          label,
        };

        const updated = saveRememberedAccount(account);
        setRememberedAccounts(updated);

        if (autoSwitch) {
          clearAuthToken();
          setToken(null);
          setSubscription(null);
          setTokenInput("");
          setSignInError(null);
        } else {
          setToken(trimmed);
          setSubscription(res.data);
          setCurrentUser(user);
          setCurrentRole(role);
          setActiveTab("tools");
          setTokenInput("");
          setSignInError(null);

          // Adjust operation if Basic plan
          if (res.data.plan === "Basic" && operation === "process") {
            setOperation("validate");
          }
        }
      } else {
        clearAuthToken();
        setToken(null);
        setSubscription(null);
        setSignInError("Token not accepted");
      }
    } catch {
      clearAuthToken();
      setToken(null);
      setSubscription(null);
      setSignInError("Token not accepted");
    } finally {
      setValidating(false);
    }
  };

  // Switch user: clears active token and returns to sign-in panel
  const handleSwitchUser = () => {
    clearAuthToken();
    setToken(null);
    setSubscription(null);
    setSubmitResult(null);
    setRuns([]);
    setSelectedRunId(null);
    setSignInError(null);
    setTokenInput("");
    setRememberedAccounts(getRememberedAccounts());
  };

  // Mount effect: handle 401 callback, URL ?token=, and existing sessionStorage
  useEffect(() => {
    // Intercept 401 mid-session and return to panel
    setOnUnauthorized(() => {
      clearAuthToken();
      setToken(null);
      setSubscription(null);
      setSignInError("Token not accepted");
      setValidating(false);
      setRememberedAccounts(getRememberedAccounts());
    });

    setRememberedAccounts(getRememberedAccounts());

    // 1. Check URL query token (?token=...)
    const params = new URLSearchParams(window.location.search);
    const autoSwitch = params.get("switch") === "1";
    const urlToken = checkAndConsumeUrlToken();
    if (urlToken) {
      validateAndSignIn(urlToken, autoSwitch);
      return;
    }

    // 2. Check existing sessionStorage token
    const stored = getAuthToken();
    if (stored) {
      validateAndSignIn(stored);
    }
  }, []);

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
        if (res.data.plan === "Basic" && operation === "process") {
          setOperation("validate");
        }
      } else if (res.status === 401) {
        clearAuthToken();
        setToken(null);
        setSubscription(null);
        setSignInError("Token not accepted");
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
      } else if (res.status === 401) {
        clearAuthToken();
        setToken(null);
        setSubscription(null);
        setSignInError("Token not accepted");
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
      } else if (res.status === 401) {
        clearAuthToken();
        setToken(null);
        setSubscription(null);
        setSignInError("Token not accepted");
      }
    } catch (e) {
      console.error("Error loading run result:", e);
    } finally {
      setResultLoading(false);
    }
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
      if (res.status === 401) {
        clearAuthToken();
        setToken(null);
        setSubscription(null);
        setSignInError("Token not accepted");
        return;
      }
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

        {/* Tenant context, user identity and quota indicators */}
        {subscription && (
          <div className="tenant-bar">
            <div className="user-identity-box" title="Authenticated User Profile">
              <span className="user-identity-name">{currentUser}</span>
              <span className="user-identity-role">{currentRole}</span>
            </div>
            <div className="tenant-name-chip" title="Tenant Organization">
              {subscription.name}
            </div>
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
          <button className="btn btn-secondary" onClick={handleSwitchUser} title="Switch to another user">
            Switch user
          </button>
        )}
      </header>

      {/* Subscription Notice Alert */}
      {subError && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          <strong>Subscription Notice:</strong> {subError}
        </div>
      )}

      {/* SIGN-IN PANEL: Displayed when not authenticated or on 401 */}
      {!token && (
        <div className="sign-in-wrapper">
          <div className="card sign-in-card">
            <h2 className="card-title">Sign in</h2>
            <p className="sign-in-explanation">
              Tokens are issued to testers to evaluate tenant data isolation and features.
            </p>

            {signInError && (
              <div className="alert alert-error" role="alert" style={{ marginBottom: 16 }}>
                <strong>{signInError}</strong>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                validateAndSignIn(tokenInput);
              }}
            >
              <div className="form-group">
                <label htmlFor="test-token-input" className="form-label">
                  Paste your test token
                </label>
                <textarea
                  id="test-token-input"
                  className="input-code sign-in-textarea"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Paste your test token here..."
                  rows={4}
                  required
                  aria-required="true"
                />
              </div>

              <div className="btn-group">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={validating || !tokenInput.trim()}
                >
                  {validating ? "Validating token..." : "Sign in"}
                </button>
              </div>
            </form>

            {rememberedAccounts.length > 0 && (
              <div className="remembered-accounts-section">
                <span className="form-label">Saved test sessions (one-click switch)</span>
                <div className="remembered-list" role="list">
                  {rememberedAccounts.map((acc, index) => (
                    <button
                      key={`${acc.user}-${acc.tenant}-${index}`}
                      type="button"
                      className="btn btn-secondary remembered-btn"
                      onClick={() => validateAndSignIn(acc.token)}
                      disabled={validating}
                      aria-label={`Sign in as ${acc.label}`}
                    >
                      <span className="remembered-indicator" aria-hidden="true">●</span>
                      <span className="remembered-label">{acc.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
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
