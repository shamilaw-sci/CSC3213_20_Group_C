import api from '@/lib/api-client';

export const AuthService = {
  login: async (credentials: { email: string; password: string }) => {
    const response = await api.post('/auth/login', credentials);
    return response.data; // { access_token, refresh_token, user }
  },

  register: async (userData: { email: string; password: string; role_id?: number }) => {
    const response = await api.post('/auth/register', userData);
    return response.data;
  },

  refresh: async (refreshToken: string) => {
    const response = await api.post('/auth/refresh', { refresh_token: refreshToken });
    return response.data; // { access_token, refresh_token }
  },

  logout: () => {
    // Zustand's logout() clears the persisted store — nothing else needed
  },
};
