import api from '@/lib/api-client';

export interface StaffUser {
  id: string;
  email: string;
  roles?: { role_name: string };
}

export const UsersService = {
  listUsers: async () => {
    const response = await api.get<StaffUser[]>('/auth/users');
    return response.data;
  },
};