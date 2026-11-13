import api from '@/lib/api-client';

export const AuthService = {
  login: async (credentials: any) => {
    // The caller hands the token to useAuthStore.setAuth, the one place it is
    // kept. It used to be copied to localStorage here as well, and sign-out
    // never removed that copy.
    const response = await api.post('/auth/login', credentials);
    return response.data;
  },
  
  register: async (userData: any) => {
    const response = await api.post('/auth/register', userData);
    return response.data;
  },
  
  getUsers: async () => {
    const response = await api.get('/auth/users');
    return response.data;
  },
  
  updateUserRole: async (userId: string, roleId: number) => {
    const response = await api.put(`/auth/users/${userId}/role`, { role_id: roleId });
    return response.data;
  },
  
  deleteUser: async (userId: string) => {
    const response = await api.delete(`/auth/users/${userId}`);
    return response.data;
  }
};
