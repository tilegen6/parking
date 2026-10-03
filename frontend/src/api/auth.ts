// Клиент аутентификации: логин, текущий пользователь.
import { api } from "./client";

export type UserRole = "admin" | "operator" | "list_manager";

export interface AuthUser {
  id: number;
  username: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export function login(username: string, password: string) {
  return api.post<LoginResponse>("/api/v1/auth/login", { username, password });
}

export function getMe() {
  return api.get<AuthUser>("/api/v1/auth/me");
}

// --- Управление пользователями (admin) ---
export interface UserCreateInput {
  username: string;
  password: string;
  full_name?: string | null;
  role: UserRole;
  is_active?: boolean;
}

export interface UserUpdateInput {
  password?: string;
  full_name?: string | null;
  role?: UserRole;
  is_active?: boolean;
}

export interface AuditEntry {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  entity: string | null;
  entity_id: string | null;
  detail: string | null;
  created_at: string;
}
