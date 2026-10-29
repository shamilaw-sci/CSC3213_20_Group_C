'use client';

import { useAuthStore } from '@/store/useAuthStore';
import { useRouter, usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { hasAnyPermission, Permission } from '@/lib/permissions';
import ChatWidget from '@/components/shared/ChatWidget';

interface ProtectedRouteProps {
  children: React.ReactNode;
  // A list means any of them.
  requiredPermission?: Permission | Permission[];
}

export default function ProtectedRoute({ children, requiredPermission }: ProtectedRouteProps) {
  const { isAuthenticated, user } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isAuthenticated && pathname !== '/login') {
      router.push('/login');
    } else if (isAuthenticated && pathname === '/login') {
      router.push('/dashboard');
    } else if (isAuthenticated && user && requiredPermission && !hasAnyPermission(user.role, requiredPermission)) {
      router.push('/unauthorized'); // Redirect to unauthorized page
    }
  }, [isAuthenticated, user, router, pathname, requiredPermission]);

  if (!isAuthenticated && pathname !== '/login') {
    return null; // Or a loading skeleton
  }

    return (
    <>
      {children}
      {isAuthenticated && pathname !== '/login' && <ChatWidget />}
    </>
  );
}
