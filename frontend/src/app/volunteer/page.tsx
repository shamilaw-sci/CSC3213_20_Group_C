// frontend/src/app/volunteer/page.tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { VolunteersService, SKILLS, AVAILABILITY } from '@/services/volunteers.service';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Loader2, CheckCircle2, HeartHandshake } from 'lucide-react';
import { cn, getErrorMessage } from '@/lib/utils';

type Step = 'form' | 'submitting' | 'done';

export default function VolunteerApplyPage() {
  const [step, setStep] = useState<Step>('form');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [skills, setSkills] = useState<string[]>([]);
  const [skillsOther, setSkillsOther] = useState('');
  const [availability, setAvailability] = useState<string[]>([]);

  function toggle(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!fullName.trim()) {
      toast.error('Please tell us your name.');
      return;
    }
    if (!email.trim()) {
      toast.error('Please give us an email address so we can reach you.');
      return;
    }
    if (availability.length === 0) {
      toast.error('Please pick at least one time you could help.');
      return;
    }

    setStep('submitting');
    try {
      await VolunteersService.apply({
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        skills,
        skills_other: skillsOther.trim() || undefined,
        availability,
      });
      setStep('done');
    } catch (err) {
      toast.error(
        getErrorMessage(err) || "Couldn't submit your application. Please try again."
      );
      setStep('form');
    }
  }

  return (
    <div className="min-h-screen bg-bg-subtle text-text-primary">
      {/* Hero in the donate page's shape: fixed height, bg-cover photo,
          gradient at the bottom only, heading sitting on the bottom edge.
          volunteer.jpg is a single photo rather than a collage, so unlike
          rescue-report.png on /report it crops cleanly and does not need to
          keep its natural aspect. */}
      <section className="relative h-[420px] md:h-[480px] overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/images/volunteer.jpg')" }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-black/10" />
        <div className="relative h-full max-w-3xl mx-auto px-4 flex flex-col items-center justify-end text-center space-y-4 pb-14">
          <HeartHandshake className="w-10 h-10 text-[#EF9F27]" />
          <h1 className="text-4xl md:text-5xl font-bold font-heading text-white tracking-tight">
            Volunteer with us
          </h1>
          <p className="text-base md:text-lg text-white/85 max-w-xl leading-relaxed">
            Give what time you can — clinics, transport, fostering or a few hours
            of admin. Every bit helps an animal.
          </p>
        </div>
      </section>

      <section className="max-w-lg mx-auto px-4 -mt-10 mb-16 relative">
        <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card">
          <CardContent className="pt-6 space-y-6">
            {step === 'done' ? (
              // No mention of whether a record was created. The API returns the
              // same response for a fresh application and a duplicate, so that
              // the form cannot be used to test whether an address is already
              // registered — saying more here would undo that.
              <div className="py-8 flex flex-col items-center gap-3 text-center">
                <CheckCircle2 className="w-10 h-10 text-[#EF9F27]" />
                <h2 className="text-lg font-bold font-heading">Thank you!</h2>
                <p className="text-sm text-text-secondary leading-relaxed max-w-sm">
                  We have your details. Someone from the team will review your
                  application and get in touch — keep an eye on your email, and
                  do check the spam folder.
                </p>
                <Link href="/" className="text-sm text-[#EF9F27] hover:underline mt-2">
                  Back to home
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    Your name
                  </label>
                  <Input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Nimal Perera"
                    maxLength={120}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    Email
                  </label>
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    Phone{' '}
                    <span className="text-text-muted normal-case font-normal">
                      (optional, but WhatsApp is how we usually reach people)
                    </span>
                  </label>
                  <Input
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="07X XXX XXXX"
                    maxLength={40}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    What could you help with?{' '}
                    <span className="text-text-muted normal-case font-normal">(optional)</span>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {SKILLS.map((s) => (
                      <button
                        key={s.value}
                        type="button"
                        onClick={() => toggle(skills, setSkills, s.value)}
                        aria-pressed={skills.includes(s.value)}
                        className={cn(
                          'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                          skills.includes(s.value)
                            ? 'bg-[#EF9F27] text-white border-[#EF9F27]'
                            : 'border-border-brand text-text-secondary hover:border-[#EF9F27]/50'
                        )}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                  <Input
                    value={skillsOther}
                    onChange={(e) => setSkillsOther(e.target.value)}
                    placeholder="Anything else you can offer?"
                    maxLength={500}
                    className="mt-2"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    When are you usually free?
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {AVAILABILITY.map((a) => (
                      <button
                        key={a.value}
                        type="button"
                        onClick={() => toggle(availability, setAvailability, a.value)}
                        aria-pressed={availability.includes(a.value)}
                        className={cn(
                          'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                          availability.includes(a.value)
                            ? 'bg-[#EF9F27] text-white border-[#EF9F27]'
                            : 'border-border-brand text-text-secondary hover:border-[#EF9F27]/50'
                        )}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                </div>

                <p className="text-xs text-text-muted leading-relaxed">
                  Volunteers do not get a login. Once you are approved we will
                  send you a personal link showing what you have been asked to
                  help with — no password to remember.
                </p>

                <Button
                  type="submit"
                  disabled={step === 'submitting'}
                  className="w-full bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90 hover:scale-[1.02] shadow-lg shadow-amber-500/20 transition-all"
                >
                  {step === 'submitting' ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      Submitting...
                    </>
                  ) : (
                    'Submit application'
                  )}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
