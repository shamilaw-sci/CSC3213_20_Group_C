'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AuthService } from '@/services/auth.service';
import { useAuthStore } from '@/store/useAuthStore';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { LogIn, Mail, Lock } from 'lucide-react';
import Link from 'next/link';
import { getErrorMessage } from '@/lib/utils';
import AuthShell from '@/components/auth/AuthShell';
import AuthField from '@/components/auth/AuthField';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const setAuth = useAuthStore((state) => state.setAuth);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const data = await AuthService.login({ email, password });
      setAuth(data.user, data.access_token);
      toast.success('Access granted. Welcome back.');
      router.push('/dashboard');
    } catch (err) {
      toast.error(getErrorMessage(err) || 'Authentication failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Authorize access"
      subtitle="Sign in to continue to your dashboard."
      footer={
        <p className="text-xs text-text-secondary flex justify-between">
          <span>
            Need an account?{' '}
            <Link href="/register" className="text-[#EF9F27] hover:underline font-semibold">
              Register here
            </Link>
          </span>
          <Link href="/login/admin" className="text-[#EF9F27] hover:underline font-semibold">
            Admin Portal
          </Link>
        </p>
      }
    >
      <form onSubmit={handleLogin} className="space-y-4">
        <AuthField
          icon={Mail}
          id="email"
          type="email"
          placeholder="Email Address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        <AuthField
          icon={Lock}
          id="password"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <Button
          type="submit"
          className="w-full bg-[#EF9F27] hover:bg-[#EF9F27]/80 text-[#0B0D12] font-semibold text-xs py-3 px-6 mt-2 transition-all rounded-lg active:scale-95 h-11 flex items-center justify-center gap-2 border-none shadow-md shadow-[#EF9F27]/10"
          disabled={loading}
        >
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#0B0D12] border-t-transparent" />
              Verifying...
            </>
          ) : (
            <>
              <LogIn size={16} />
              Authorize Access
            </>
          )}
        </Button>
      </form>
    </AuthShell>
  );
}
