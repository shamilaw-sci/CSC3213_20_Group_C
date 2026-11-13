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
    }
  )
);
