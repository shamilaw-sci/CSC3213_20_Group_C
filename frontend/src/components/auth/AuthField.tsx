'use client';

import { useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Eye, EyeOff } from 'lucide-react';
import { Input } from '@/components/ui/input';

// The icon-plus-input block was repeated nine times across the auth pages,
// each with the same long className. Password fields own their own reveal
// toggle here, so on the register screen the password and confirm fields
// can be revealed independently.
export default function AuthField({
  icon: Icon,
  type = 'text',
  ...props
}: {
  icon: LucideIcon;
  type?: string;
} & Omit<React.ComponentProps<typeof Input>, 'type'>) {
  const [reveal, setReveal] = useState(false);
  const isPassword = type === 'password';
  const resolvedType = isPassword && reveal ? 'text' : type;

  return (
    <div className="relative">
      <Icon
        className="absolute left-4 top-[14px] text-text-secondary/40 pointer-events-none"
        size={16}
      />
      <Input
        type={resolvedType}
        className={`pl-11 ${isPassword ? 'pr-10' : ''} bg-bg-subtle border-border-brand text-text-primary focus:border-[#EF9F27] focus:ring-1 focus:ring-[#EF9F27] h-11 rounded-lg w-full placeholder:text-text-secondary/40 text-xs`}
        {...props}
      />
      {isPassword && (
        <button
          type="button"
          onClick={() => setReveal((v) => !v)}
          aria-label={reveal ? 'Hide password' : 'Show password'}
          className="absolute right-4 top-[14px] text-text-secondary/40 hover:text-text-primary transition-colors"
        >
          {reveal ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      )}
    </div>
  );
}
