import type { Tenant } from "./tenant";
import type { Role, User } from "./user";

export interface AuthResponse {
  access: string;
  refresh: string;
  user: User;
  tenant: Tenant | null;
  role: Role | null;
}

export interface JWTPayload {
  user_id: string;
  tenant_id?: string;
  role?: Role;
  exp: number;
  iat: number;
  token_type: "access" | "refresh";
  jti: string;
}
