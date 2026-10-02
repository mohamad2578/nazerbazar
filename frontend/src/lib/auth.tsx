import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokens } from "./api";

export type Role = "admin" | "governorate" | "chamber" | "union" | "store" | "citizen";

export type Me = {
  id: number;
  mobile: string;
  first_name: string;
  last_name: string;
  national_code: string;
  role: Role;
  role_display: string;
  province: number | null;
  chamber: number | null;
  union: number | null;
  scope_name: string;
  store: null | { id: number; name: string; status: string; status_display: string; status_reason: string; union_name: string };
};

type Ctx = {
  user: Me | null;
  loading: boolean;
  login: (payload: { access: string; refresh: string; user: Me }) => void;
  logout: () => void;
  reload: () => Promise<void>;
};

const AuthContext = createContext<Ctx>(null as never);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(!!tokens.get());

  const reload = useCallback(async () => {
    if (!tokens.get()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.get<Me>("/auth/me/"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    const onLogout = () => setUser(null);
    window.addEventListener("nb:logout", onLogout);
    return () => window.removeEventListener("nb:logout", onLogout);
  }, [reload]);

  const login: Ctx["login"] = (p) => {
    tokens.set({ access: p.access, refresh: p.refresh });
    setUser(p.user);
  };
  const logout = () => {
    tokens.set(null);
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, loading, login, logout, reload }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export const isPanelUser = (u: Me | null) => !!u && (u.role !== "citizen" || !!u.store);

export const ROLE_LABEL: Record<Role, string> = {
  admin: "مدیر کل",
  governorate: "استانداری",
  chamber: "اتاق اصناف",
  union: "اتحادیه",
  store: "فروشگاه",
  citizen: "شهروند",
};
