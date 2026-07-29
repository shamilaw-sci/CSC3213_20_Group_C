import axios from 'axios';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Mocking behavior for demo
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    let token: string | null = null;

    const storage = localStorage.getItem('vff-auth-storage');
    if (storage) {
      try {
        const { state } = JSON.parse(storage);
        token = state?.token || null;
      } catch {
        token = null;
      }
    }

    if (!token) {
      token = localStorage.getItem('auth_token');
    }

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});


export default api;
