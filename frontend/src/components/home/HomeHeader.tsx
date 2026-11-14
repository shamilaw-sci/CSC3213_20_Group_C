'use client';

import { useState, useEffect, useRef } from 'react';
import { useAuthStore } from '@/store/useAuthStore';
import { useThemeStore } from '@/store/useThemeStore';
import { ArrowRight, Bell, User, Settings, HelpCircle, LogOut, Sun, Moon, Heart } from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter } from 'next/navigation';

export default function HomeHeader() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { theme, toggleTheme } = useThemeStore();
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfile, setShowProfile] = useState(false);

  const notifRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  const notifications = [
    { id: 1, text: "New transaction approved by Director", time: "5 mins ago" },
    { id: 2, text: "Annual medical inventory audit scheduled", time: "1 hour ago" },
    { id: 3, text: "System database backup complete", time: "4 hours ago" }
  ];

  // Click outside listener
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setShowProfile(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Scroll sensitive Navbar (hide on scroll down, show on scroll up)
  const [navVisible, setNavVisible] = useState(true);
  const [lastScrollY, setLastScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      if (currentScrollY > lastScrollY && currentScrollY > 80) {
        setNavVisible(false);
      } else {
        setNavVisible(true);
      }
      setLastScrollY(currentScrollY);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [lastScrollY]);

  return (
    <header className={`fixed top-0 left-0 right-0 z-50 border-b border-border-brand bg-bg-brand/90 backdrop-blur-md transition-transform duration-300 ${
      navVisible ? 'translate-y-0' : '-translate-y-full'
    }`}>
      <div className="max-w-[1280px] mx-auto px-6 md:px-12 h-16 flex justify-between items-center">
        <Link href="/" className="flex items-center gap-2.5 hover:opacity-90 transition-opacity">
          <Image src="/images/vff-logo.png" alt="Vets For Future" width={36} height={36} priority className="h-9 w-9 object-contain" />
          <span className="text-sm font-extrabold tracking-wider uppercase text-text-primary">
            VFF IMS
          </span>
        </Link>
        <nav className="flex items-center gap-6 text-xs font-semibold text-text-secondary">
          <Link href="/" className="hover:text-text-primary transition-colors duration-150">Home</Link>
          <Link href="/who-we-are" className="hover:text-text-primary transition-colors duration-150">Who We Are</Link>
          <Link href="/report" className="hover:text-text-primary transition-colors duration-150">Report an Animal</Link>
          <Link href="/clinics" className="hover:text-text-primary transition-colors duration-150">Clinics</Link>
          <Link href="/outbreak-map" className="hover:text-text-primary transition-colors duration-150">Hotspot Map</Link>
          <Link href="/volunteer" className="hover:text-text-primary transition-colors duration-150">Volunteer</Link>
          <Link
            href="/donate"
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-[#EF9F27] text-bg-brand font-bold hover:bg-[#EF9F27]/90 hover:shadow-md hover:shadow-[#EF9F27]/30 transition-all"
          >
            <Heart className="w-3.5 h-3.5" fill="currentColor" />
            Donate
          </Link>
          {isAuthenticated ? (
            <>
              <Link href="/dashboard" className="text-[#EF9F27] hover:text-[#EF9F27]/80 flex items-center gap-1 font-semibold">
                Dashboard <ArrowRight size={14} />
              </Link>

              {/* Notification Bell */}
              <div className="relative" ref={notifRef}>
                <button
                  onClick={() => setShowNotifications(!showNotifications)}
                  className="relative p-1.5 text-text-secondary hover:text-text-primary rounded-lg hover:bg-bg-subtle transition-colors flex items-center"
                >
                  <Bell className="w-5 h-5" />
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#EF9F27]" />
                </button>

                {showNotifications && (
                  <div className="absolute right-0 mt-2 w-80 bg-surface border border-border-brand rounded-xl shadow-xl overflow-hidden animate-in fade-induration-100 z-50 text-left">
                    <div className="px-4 py-2 border-b border-border-brand">
                      <span className="text-xs font-semibold text-text-primary font-heading">Notifications</span>
                    </div>
                    <div className="divide-y divide-border-brand">
                      {notifications.map((n) => (
                        <div key={n.id} className="p-3 hover:bg-bg-subtle cursor-pointer transition-colors">
                          <p className="text-xs text-text-secondary leading-normal">{n.text}</p>
                          <span className="text-[10px] text-text-muted mt-1 block font-mono">{n.time}</span>
                        </div>
                      ))}
                    </div>
                    <div className="p-2 border-t border-border-brand text-center bg-bg-subtle/50">
                      <Link href="/dashboard" className="text-[11px] text-[#EF9F27] hover:underline font-semibold" onClick={() => setShowNotifications(false)}>
                        View all notifications
                      </Link>
                    </div>
                  </div>
                )}
              </div>

              {/* User Profile Avatar Dropdown */}
              <div className="relative" ref={profileRef}>
                <button
                  onClick={() => setShowProfile(!showProfile)}
                  className="flex items-center gap-2 p-1 text-text-secondary hover:text-text-primary rounded-full hover:bg-bg-subtle transition-all"
                >
                  <div className="flex items-center justify-center w-8 h-8 rounded-full bg-amber-500/10 border border-[#EF9F27]/25 text-[#EF9F27] text-sm font-bold shadow-sm shadow-[#EF9F27]/5">
                    {user?.name ? user.name[0].toUpperCase() : 'U'}
                  </div>
                </button>

                {showProfile && (
                  <div className="absolute right-0 mt-2 w-56 bg-surface border border-border-brand rounded-xl shadow-xl overflow-hidden animate-in fade-induration-100 z-50 text-left">
                    <div className="px-4 py-3 border-b border-border-brand bg-bg-subtle/30">
                      <p className="text-xs font-semibold text-text-primary truncate font-heading">{user?.name || 'User'}</p>
                      <p className="text-[10px] text-text-secondary truncate mt-0.5 font-mono">{user?.email || 'user@example.com'}</p>
                    </div>
                    <div className="p-1">
                      <button
                        onClick={() => { router.push('/profile'); setShowProfile(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-left text-xs text-text-secondary hover:bg-bg-subtle hover:text-text-primary rounded-lg transition-colors font-medium"
                      >
                        <User className="w-3.5 h-3.5" />
                        <span>Edit profile</span>
                      </button>
                      <button
                        onClick={() => { router.push('/settings'); setShowProfile(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-left text-xs text-text-secondary hover:bg-bg-subtle hover:text-text-primary rounded-lg transition-colors font-medium"
                      >
                        <Settings className="w-3.5 h-3.5" />
                        <span>Account settings</span>
                      </button>
                      <button
                        onClick={() => { router.push('/support'); setShowProfile(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-left text-xs text-text-secondary hover:bg-bg-subtle hover:text-text-primary rounded-lg transition-colors font-medium"
                      >
                        <HelpCircle className="w-3.5 h-3.5" />
                        <span>Support</span>
                      </button>
                      {/* Theme Mode Toggle Dropdown item */}
                      <button
                        onClick={() => { toggleTheme(); setShowProfile(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-left text-xs text-text-secondary hover:bg-bg-subtle hover:text-text-primary rounded-lg transition-colors font-medium"
                      >
                        {theme === 'dark' ? (
                          <>
                            <Sun className="w-3.5 h-3.5 text-[#EF9F27]" />
                            <span>Switch to Light Mode</span>
                          </>
                        ) : (
                          <>
                            <Moon className="w-3.5 h-3.5 text-[#EF9F27]" />
                            <span>Switch to Dark Mode</span>
                          </>
                        )}
                      </button>
                    </div>
                    <div className="p-1 border-t border-border-brand bg-bg-subtle/20">
                      <button
                        onClick={() => { logout(); setShowProfile(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-left text-xs text-[#DC2626] hover:bg-rose-500/10 rounded-lg transition-colors font-semibold"
                      >
                        <LogOut className="w-3.5 h-3.5" />
                        <span>Sign out</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <Link href="/login" className="hover:text-text-primary transition-colors duration-150">Login</Link>
              <Link href="/register" className="hover:text-text-primary transition-colors duration-150">Register</Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}