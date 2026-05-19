import axios from 'axios';
import { useAuthStore } from '@/store/useAuthStore';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Request interceptor: attach current access token ────────────────────────
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const storage = localStorage.getItem('vff-auth-storage');
    if (storage) {
      try {
        const { state } = JSON.parse(storage);
        if (state?.token) {
          config.headers.Authorization = `Bearer ${state.token}`;
        }
      } catch { /* ignore parse errors */ }
    }
  }
  return config;
});

// ─── Response interceptor: auto-refresh on 401 ───────────────────────────────
let isRefreshing = false;
let failedQueue: Array<{ resolve: (v: string) => void; reject: (e: any) => void }> = [];

function processQueue(error: any, token: string | null) {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)));
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Only attempt refresh on 401, and only once per request
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't retry the refresh endpoint itself — that would loop forever
      if (originalRequest.url?.includes('/auth/refresh')) {
        useAuthStore.getState().logout();
        if (typeof window !== 'undefined') window.location.href = '/login';
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Queue this request until the ongoing refresh completes
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const storage = localStorage.getItem('vff-auth-storage');
        const { state } = JSON.parse(storage ?? '{}');
        const refreshToken = state?.refreshToken;

        if (!refreshToken) throw new Error('No refresh token');

        // Call our backend refresh endpoint
        const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });

        const newAccessToken: string = data.access_token;
        const newRefreshToken: string = data.refresh_token;

        // Update the store with the new tokens
        useAuthStore.getState().setTokens(newAccessToken, newRefreshToken);

        // Retry the queued requests with the new token
        processQueue(null, newAccessToken);
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        useAuthStore.getState().logout();
        if (typeof window !== 'undefined') window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
