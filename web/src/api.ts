// Typed API client for Customer Data Quality SaaS

export interface ErrorDetail {
  code: string;
  message: string;
}

export interface SubscriptionInfo {
  tenant_id: string;
  name: string;
  plan: "Basic" | "Pro";
  status: "Active" | "Suspended";
  daily_quota: number;
  used_quota: number;
  remaining_quota: number;
  allowed_operations: string[];
}

export interface ValidationIssue {
  row_index: number;
  field: string;
  rule_id: string;
}

export interface ValidationResult {
  valid_rows: number;
  invalid_rows: number;
  issues: ValidationIssue[];
}

export interface ProcessedRow {
  record_id: string;
  email: string;
  contactable: boolean;
}

export interface ProcessResult {
  summary: {
    input_rows: number;
    contactable_rows: number;
  };
  rows: ProcessedRow[];
  issues: ValidationIssue[];
}

export interface RunItem {
  run_id: string;
  tenant_id?: string;
  idempotency_key: string;
  operation: "validate" | "process";
  status: "Running" | "Succeeded" | "Failed";
  created_at: string;
  finished_at?: string;
}

export interface RunResultResponse {
  run_id: string;
  status: "Running" | "Succeeded" | "Failed";
  result?: ValidationResult | ProcessResult;
  error?: ErrorDetail;
}

export interface CreateRunResponse {
  run_id: string;
  status: "Succeeded" | "Failed";
  result?: ValidationResult | ProcessResult;
  error?: ErrorDetail;
}

// Token management in-memory & sessionStorage
let inMemoryToken: string | null = null;

export interface RememberedAccount {
  token: string;
  user: string;
  tenant: string;
  role: string;
  label: string;
}

const REMEMBERED_STORAGE_KEY = "saas_remembered_accounts";
const AUTH_TOKEN_KEY = "saas_auth_token";

export function getRememberedAccounts(): RememberedAccount[] {
  try {
    const raw = sessionStorage.getItem(REMEMBERED_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.slice(0, 4);
    }
    return [];
  } catch {
    return [];
  }
}

export function saveRememberedAccount(account: RememberedAccount): RememberedAccount[] {
  try {
    const existing = getRememberedAccounts();
    const filtered = existing.filter((a) => a.token !== account.token && a.label !== account.label);
    const updated = [account, ...filtered].slice(0, 4);
    sessionStorage.setItem(REMEMBERED_STORAGE_KEY, JSON.stringify(updated));
    return updated;
  } catch {
    return [];
  }
}

export function parseTokenClaims(token: string): { user?: string; role?: string; tenant_id?: string; exp?: number } | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

export function checkAndConsumeUrlToken(): string | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const tokenFromUrl = params.get("token");
  if (tokenFromUrl) {
    params.delete("token");
    const newSearch = params.toString();
    const newUrl = window.location.pathname + (newSearch ? `?${newSearch}` : "") + window.location.hash;
    window.history.replaceState({}, document.title, newUrl);
    return tokenFromUrl;
  }
  return null;
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setOnUnauthorized(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

export function initAuthToken(): string | null {
  const urlToken = checkAndConsumeUrlToken();
  if (urlToken) {
    inMemoryToken = urlToken;
    sessionStorage.setItem(AUTH_TOKEN_KEY, urlToken);
    return urlToken;
  }

  const storedToken = sessionStorage.getItem(AUTH_TOKEN_KEY);
  if (storedToken) {
    inMemoryToken = storedToken;
    return storedToken;
  }

  return null;
}

export function getAuthToken(): string | null {
  return inMemoryToken || sessionStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  inMemoryToken = token;
  sessionStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  inMemoryToken = null;
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<{ status: number; data: T }> {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearAuthToken();
    if (unauthorizedHandler) {
      unauthorizedHandler();
    }
  }

  const contentType = response.headers.get("content-type");
  let data: any = null;
  if (contentType && contentType.includes("application/json")) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  return { status: response.status, data };
}

export const api = {
  getHealth: () => request<{ status: string }>("/health"),
  getSubscription: () => request<SubscriptionInfo>("/subscription"),
  getRuns: () => request<{ runs: RunItem[] }>("/runs"),
  getRunResult: (runId: string) => request<RunResultResponse>(`/runs/${runId}/result`),
  createRun: (operation: "validate" | "process", records: any[], idempotencyKey: string) =>
    request<CreateRunResponse>("/runs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ operation, records }),
    }),
};
