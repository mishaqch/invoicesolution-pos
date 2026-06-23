/**
 * Tiny fetch wrapper for the public lead endpoint. Same-origin in production
 * (the marketing site and the Django backend share the apex host via nginx),
 * and proxied to localhost:8000 in dev (see vite.config.ts).
 */

export interface LeadPayload {
  name: string;
  business_name: string;
  phone: string;
  email?: string;
  city?: string;
  business_type?: string;
  product_interest: "pos" | "digital_invoicing" | "both" | "";
  message?: string;
  /** Honeypot — must stay empty; bots fill it. */
  company_website?: string;
}

export class LeadError extends Error {
  fields?: Record<string, string[]>;
  constructor(message: string, fields?: Record<string, string[]>) {
    super(message);
    this.fields = fields;
  }
}

export async function submitLead(payload: LeadPayload): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/leads/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new LeadError(
      "We couldn't reach our servers. Please check your connection or message us on WhatsApp.",
    );
  }

  if (res.ok) return;

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error body */
  }

  if (res.status === 429) {
    throw new LeadError("You've sent a few requests already — please try again in a minute.");
  }
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (typeof obj.detail === "string") throw new LeadError(obj.detail);
    // DRF field errors: { field: ["msg", ...] }
    const fields: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(obj)) {
      if (Array.isArray(v)) fields[k] = v.map(String);
    }
    if (Object.keys(fields).length) {
      throw new LeadError("Please check the highlighted fields.", fields);
    }
  }
  throw new LeadError("Something went wrong. Please try again or message us on WhatsApp.");
}
