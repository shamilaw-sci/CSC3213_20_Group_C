import axios from 'axios';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// The token comes from the auth store only, so signing out (which clears the
// store) stops it being sent.
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

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});


export default api;
