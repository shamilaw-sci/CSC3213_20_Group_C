'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AuthService } from '@/services/auth.service';
import { useAuthStore } from '@/store/useAuthStore';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Mail, Lock, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import { getErrorMessage } from '@/lib/utils';
import AuthShell from '@/components/auth/AuthShell';
import AuthField from '@/components/auth/AuthField';

export default function AdminRegisterPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const router = useRouter();
  const setAuth = useAuthStore((state) => state.setAuth);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast.error('Passwords do not match.');
      return;
    }
    setLoading(true);

    try {
      // Mock name extraction
      const mockName = email.split('@')[0];
      const data = await AuthService.register({
        email,
        password,
        name: mockName.charAt(0).toUpperCase() + mockName.slice(1) + ' (Admin)',
        role: 'Admin',
      });

      setAuth(data.user, data.access_token);
      toast.success('Administrator registry generated successfully.');
      router.push('/dashboard');
    } catch (err) {
      toast.error(getErrorMessage(err) || 'Admin signup failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Create admin account"
      subtitle={
        <span className="flex items-center gap-1.5">
          <ShieldCheck size={13} className="text-[#EF9F27] shrink-0" />
          Creates an account with full administrator privileges.
        </span>
      }
      footer={
        <p className="text-xs text-text-secondary text-center">
          Already have an account?{' '}
          <Link href="/login/admin" className="text-[#EF9F27] hover:underline font-semibold">
            Admin sign in
          </Link>
        </p>
      }
    >
      <form onSubmit={handleRegister} className="space-y-4">
        <AuthField
          icon={Mail}
          id="email"
          type="email"
          placeholder="Admin Email Address"
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

        <AuthField
          icon={Lock}
          id="confirm-password"
          type="password"
          placeholder="Confirm Password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
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
              Creating Account...
            </>
          ) : (
            <>
              <ShieldCheck size={16} />
              Create Admin Account
            </>
          )}
        </Button>
      </form>
    </AuthShell>
  );
}
