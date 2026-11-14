import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { User, UserRole } from '@/types';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, token: string) => void;
  setUser: (user: User) => void;
  logout: () => void;
}


export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      setAuth: (user, token) => {
        if (typeof window !== 'undefined') {
          document.cookie = `token=${token}; path=/; max-age=86400; SameSite=Lax; Secure`;
        }
        set({ 
          user,
          token,
          isAuthenticated: true 
        });
      },
      setUser: (user) => set({ user }),
      logout: () => {
        if (typeof window !== 'undefined') {
          document.cookie = 'token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax; Secure';
          // Copies older logins left behind, which the API client used to
          // fall back to, so a signed-out browser still sent the last token.
          localStorage.removeItem('auth_token');
          localStorage.removeItem('user_role');
        }
        set({ user: null, token: null, isAuthenticated: false });
      },

    }),
    {
      name: 'vff-auth-storage',
      // A saved session without a user or a token is not a session. The old
      // register flow saved exactly that ({ isAuthenticated: true }), and the
      // page guards, which check permissions only once there is a user,
      // rendered every page for it. Treat it as signed out instead.
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<AuthState>;
        const complete = Boolean(saved.isAuthenticated && saved.user && saved.token);
        return complete
          ? { ...current, ...saved }
          : { ...current, user: null, token: null, isAuthenticated: false };
      },
    }
  )
);
