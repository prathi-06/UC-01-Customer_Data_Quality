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

export function initAuthToken(): string | null {
  const params = new URLSearchParams(window.location.search);
  const tokenFromUrl = params.get("token");
  if (tokenFromUrl) {
    inMemoryToken = tokenFromUrl;
    sessionStorage.setItem("saas_auth_token", tokenFromUrl);
    // Clean URL
    params.delete("token");
    const newSearch = params.toString();
    const newUrl = window.location.pathname + (newSearch ? `?${newSearch}` : "");
    window.history.replaceState({}, document.title, newUrl);
    return tokenFromUrl;
  }

  const storedToken = sessionStorage.getItem("saas_auth_token");
  if (storedToken) {
    inMemoryToken = storedToken;
    return storedToken;
  }

  return null;
}

export function getAuthToken(): string | null {
  return inMemoryToken || sessionStorage.getItem("saas_auth_token");
}

export function setAuthToken(token: string): void {
  inMemoryToken = token;
  sessionStorage.setItem("saas_auth_token", token);
}

export function clearAuthToken(): void {
  inMemoryToken = null;
  sessionStorage.removeItem("saas_auth_token");
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
