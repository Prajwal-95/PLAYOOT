import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { api, User } from "../services/api";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  loginWithPhone: (phoneNumber: string, firebaseToken: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const userData = await api.me();
      setUser(userData);
    } catch {
      localStorage.removeItem("access_token");
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  const login = async (email: string, password: string) => {
    const { access_token, user: userData } = await api.login({ email, password });
    localStorage.setItem("access_token", access_token);
    setUser(userData);
  };

  const register = async (name: string, email: string, password: string) => {
    const { access_token, user: userData } = await api.register({ name, email, password });
    localStorage.setItem("access_token", access_token);
    setUser(userData);
  };

  const loginWithPhone = async (phoneNumber: string, firebaseToken: string) => {
    const { access_token, user: userData } = await api.phoneVerify(phoneNumber, firebaseToken);
    localStorage.setItem("access_token", access_token);
    setUser(userData);
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, loginWithPhone, logout, refreshUser, setUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}