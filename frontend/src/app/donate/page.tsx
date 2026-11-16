"use client";

import ImpactNumbers from "@/components/home/ImpactNumbers";
import HomeHeader from "@/components/home/HomeHeader";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Heart, ArrowRight, Info, Loader2, Globe2, Stethoscope, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  DonationsService,
  redirectToPayHere,
  MIN_DONATION,
  MAX_DONATION,
  type DonationPurpose,
} from "@/services/donations.service";
import { cn, getErrorMessage } from "@/lib/utils";

const PRESET_AMOUNTS = [1000, 2500, 5000, 10000];

// Real VFF program categories (vetsforfuturesl.com), not a generic
// shelter-feeding line — VFF's actual model is field sterilization,
// vaccination, and free clinics, not a housing shelter.
const IMPACT_ITEMS = [
  {
    title: "Funds a sterilization procedure",
    description: "Supports the campaigns behind over a million dogs and cats sterilized nationwide since 2000.",
  },
  {
    title: "Funds a rabies vaccination",
    description: "Contributes to the 1.3 million vaccinations that have cut Sri Lanka's annual human rabies deaths from 60+ to 20-30.",
  },
  {
    title: "Supports a free clinic visit",
    description: "Helps run VFF's free animal health clinics and community outreach programs for rural communities.",
  },
];

const PURPOSES: { value: DonationPurpose; title: string; description: string; icon: typeof Globe2 }[] = [
  {
    value: "general",
    title: "Where it's needed most",
    description: "Lets us put your gift towards whichever program or clinic needs it most.",
    icon: Globe2,
  },
  {
    value: "program",
    title: "Support a specific program",
    description: "Your gift is set aside for that program only and spent on nothing else.",
    icon: Stethoscope,
  },
];

const label = "text-xs font-semibold text-text-secondary uppercase tracking-wide";

export default function DonatePage() {
  // useSearchParams needs a Suspense boundary in the app router.
  return (
    <Suspense fallback={null}>
      <DonateForm />
    </Suspense>
  );
}

function DonateForm() {
  const searchParams = useSearchParams();
  // PayHere may append its own query string to our cancel URL; keep only our id.
  const cancelledOrder = (searchParams.get("cancelled") ?? "").split("?")[0] || null;

  const [selected, setSelected] = useState<number | null>(2500);
  const [custom, setCustom] = useState("");
  const [purpose, setPurpose] = useState<DonationPurpose>("general");
  const [programId, setProgramId] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Upcoming and Active programs only; the API leaves out Completed ones.
  const { data: programs = [], isLoading: programsLoading } = useQuery({
    queryKey: ["donations", "programs"],
    queryFn: DonationsService.listPrograms,
  });

  // Back from PayHere after pressing cancel: mark that donation cancelled so
  // it does not sit as pending on the staff page. Once per order.
  const cancelHandled = useRef<string | null>(null);
  useEffect(() => {
    if (!cancelledOrder || cancelHandled.current === cancelledOrder) return;
    cancelHandled.current = cancelledOrder;
    DonationsService.cancel(cancelledOrder).catch(() => undefined);
  }, [cancelledOrder]);

  const amount = custom ? Number(custom) : selected;
  const amountValid =
    !!amount && Number.isFinite(amount) && amount >= MIN_DONATION && amount <= MAX_DONATION;

  const handleDonate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!amountValid) {
      toast.error(`Please choose an amount between LKR ${MIN_DONATION} and LKR ${MAX_DONATION.toLocaleString()}.`);
      return;
    }
    if (purpose === "program" && !programId) {
      toast.error("Please choose the program you would like to support.");
      return;
    }
    if (!anonymous && !name.trim()) {
      toast.error("Please tell us your name, or choose to donate anonymously.");
      return;
    }
    if (!anonymous && !email.trim()) {
      toast.error("Please give your email so we can thank you, or choose to donate anonymously.");
      return;
    }

    setSubmitting(true);
    try {
      const checkout = await DonationsService.checkout({
        amount: Math.round(amount! * 100) / 100,
        purpose,
        program_id: purpose === "program" ? Number(programId) : undefined,
        is_anonymous: anonymous,
        // Nothing about the donor is sent when they chose to stay anonymous.
        ...(anonymous
          ? {}
          : {
              donor_name: name.trim(),
              donor_email: email.trim(),
              donor_phone: phone.trim() || undefined,
            }),
        message: message.trim() || undefined,
      });
      // Leaves this page for PayHere; the button stays busy until it does.
      redirectToPayHere(checkout);
    } catch (err) {
      toast.error(getErrorMessage(err) || "Couldn't start your donation. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-subtle text-text-primary pt-16">
      <HomeHeader />
      {/* Hero — donate-hero.jpg was supplied directly, not sourced by me.
          Gradient sits at the bottom only, same as the homepage hero, so the
          photo itself stays visible. */}
      <section className="relative h-[420px] md:h-[480px] overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/images/donate-hero.jpg')" }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-black/10" />

        <div className="relative h-full max-w-3xl mx-auto px-4 flex flex-col items-center justify-end text-center space-y-5 pb-14">
          <Heart className="w-10 h-10 text-[#EF9F27]" fill="currentColor" />
          <h1 className="text-4xl md:text-5xl font-bold font-heading text-white tracking-tight">
            Fund a Humane Future
          </h1>
          <p className="text-base md:text-lg text-white/85 max-w-xl leading-relaxed">
            Vets For Future is the first and only organization in Sri Lanka specializing in humane animal population control. Every donation goes directly toward sterilization, vaccination, and free clinic care.
          </p>
          <ImpactNumbers variant="compact" />
        </div>
      </section>

      <section className="max-w-xl mx-auto px-4 -mt-10 mb-16 relative">
        <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card">
          <CardContent className="pt-6">
            <form onSubmit={handleDonate} className="space-y-7">
              <h2 className="text-xl font-semibold text-center font-heading">
                Make a Donation
              </h2>

              {cancelledOrder && (
                <p className="rounded-lg border border-border-brand bg-bg-subtle px-4 py-3 text-sm text-text-secondary">
                  Your payment was cancelled and nothing was charged. You can try again below.
                </p>
              )}

              {/* 1. Amount */}
              <div className="space-y-3">
                <span className={label}>Amount</span>
                <div className="grid grid-cols-2 gap-3">
                  {PRESET_AMOUNTS.map((preset) => (
                    <Button
                      key={preset}
                      type="button"
                      variant={selected === preset && !custom ? "default" : "outline"}
                      className={
                        selected === preset && !custom
                          ? "bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90 shadow-md shadow-amber-500/20"
                          : "hover:border-[#EF9F27]/40 transition-colors"
                      }
                      onClick={() => {
                        setSelected(preset);
                        setCustom("");
                      }}
                    >
                      LKR {preset.toLocaleString()}
                    </Button>
                  ))}
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="custom-amount" className="text-sm text-text-secondary">
                    Or enter your own amount (LKR)
                  </label>
                  <Input
                    id="custom-amount"
                    type="number"
                    inputMode="decimal"
                    min={MIN_DONATION}
                    max={MAX_DONATION}
                    step="0.01"
                    placeholder="e.g. 3000"
                    value={custom}
                    onChange={(e) => {
                      setCustom(e.target.value);
                      setSelected(null);
                    }}
                  />
                  {custom && !amountValid && (
                    <p className="text-xs text-negative">
                      Please enter between LKR {MIN_DONATION} and LKR {MAX_DONATION.toLocaleString()}.
                    </p>
                  )}
                </div>
              </div>

              {/* 2. Purpose */}
              <div className="space-y-3">
                <span className={label}>What would you like to support?</span>
                <div className="grid gap-3 sm:grid-cols-2">
                  {PURPOSES.map((p) => {
                    const Icon = p.icon;
                    const active = purpose === p.value;
                    return (
                      <button
                        key={p.value}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setPurpose(p.value)}
                        className={cn(
                          "text-left rounded-xl border p-4 transition-colors space-y-1.5",
                          active
                            ? "border-[#EF9F27] bg-[#EF9F27]/10"
                            : "border-border-brand hover:border-[#EF9F27]/50"
                        )}
                      >
                        <span className="flex items-center gap-2 font-semibold text-sm text-text-primary">
                          <Icon className={cn("w-4 h-4", active ? "text-[#EF9F27]" : "text-text-secondary")} />
                          {p.title}
                        </span>
                        <span className="block text-xs text-text-secondary leading-relaxed">
                          {p.description}
                        </span>
                      </button>
                    );
                  })}
                </div>

                {purpose === "program" && (
                  <div className="space-y-1.5">
                    <label htmlFor="program" className="text-sm text-text-secondary">
                      Choose a program
                    </label>
                    <select
                      id="program"
                      value={programId}
                      onChange={(e) => setProgramId(e.target.value)}
                      disabled={programsLoading}
                      className="h-9 w-full rounded-md border border-border-brand bg-surface px-3 text-sm text-text-primary"
                    >
                      <option value="">
                        {programsLoading
                          ? "Loading programs…"
                          : programs.length === 0
                            ? "No programs are taking donations right now"
                            : "Select a program"}
                      </option>
                      {programs.map((p) => (
                        <option key={p.id} value={String(p.id)}>
                          {p.program_name} ({p.status === "Active" ? "ongoing" : "upcoming"})
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* 3. Donor details */}
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3 rounded-xl border border-border-brand px-4 py-3">
                  <div className="flex items-center gap-2">
                    <EyeOff className="w-4 h-4 text-text-secondary" />
                    <span className="text-sm font-medium text-text-primary">Donate anonymously</span>
                    {/* Tooltip: hover or keyboard focus. */}
                    <span className="relative group inline-flex">
                      <button
                        type="button"
                        aria-label="What does anonymous mean?"
                        aria-describedby="anonymous-tip"
                        className="text-text-muted hover:text-text-secondary focus:outline-none focus-visible:text-text-secondary"
                      >
                        <Info className="w-4 h-4" />
                      </button>
                      <span
                        id="anonymous-tip"
                        role="tooltip"
                        className="pointer-events-none absolute left-1/2 bottom-full z-20 mb-2 w-64 -translate-x-1/2 rounded-lg bg-[#0B0D12] px-3 py-2 text-xs leading-relaxed text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
                      >
                        When this is on, we don&apos;t store your name, email or phone
                        number, so your donation stays completely private. You
                        won&apos;t get a thank-you email.
                      </span>
                    </span>
                  </div>
                  <Switch
                    checked={anonymous}
                    onCheckedChange={setAnonymous}
                    aria-label="Donate anonymously"
                  />
                </div>

                {!anonymous && (
                  <div className="space-y-4">
                    <div className="space-y-1.5">
                      <label htmlFor="donor-name" className={label}>Your name</label>
                      <Input
                        id="donor-name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="e.g. Nimal Perera"
                        maxLength={150}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label htmlFor="donor-email" className={label}>
                        Email{" "}
                        <span className="text-text-muted normal-case font-normal">
                          (we&apos;ll send your thank-you and receipt here)
                        </span>
                      </label>
                      <Input
                        id="donor-email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        maxLength={255}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label htmlFor="donor-phone" className={label}>
                        Phone <span className="text-text-muted normal-case font-normal">(optional)</span>
                      </label>
                      <Input
                        id="donor-phone"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="07X XXX XXXX"
                        maxLength={30}
                      />
                    </div>
                  </div>
                )}

                <div className="space-y-1.5">
                  <label htmlFor="donor-message" className={label}>
                    Message <span className="text-text-muted normal-case font-normal">(optional)</span>
                  </label>
                  <textarea
                    id="donor-message"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    maxLength={500}
                    rows={2}
                    placeholder="Anything you'd like us to know?"
                    className="w-full rounded-md border border-border-brand bg-transparent px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
                  />
                </div>
              </div>

              <Button
                type="submit"
                size="lg"
                disabled={!amountValid || submitting}
                className="w-full bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90 hover:scale-[1.02] shadow-lg shadow-amber-500/20 transition-all gap-2"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" /> Taking you to PayHere…
                  </>
                ) : (
                  <>
                    Donate {amountValid ? `LKR ${amount!.toLocaleString()}` : ""}
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </Button>
              <p className="text-center text-xs text-text-muted">
                Payments are processed securely by PayHere. We never see your card details.
              </p>
            </form>
          </CardContent>
        </Card>
      </section>

      {/* Impact section */}
      <section className="max-w-4xl mx-auto px-4 pb-20">
        <h2 className="text-2xl font-bold font-heading text-center mb-8">
          Your Donation Helps
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {IMPACT_ITEMS.map((item) => (
            <Card
              key={item.title}
              className="bg-surface border-border-brand/50 rounded-2xl shadow-card hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
            >
              <CardContent className="pt-6 space-y-2">
                <h3 className="font-semibold text-text-primary">
                  {item.title}
                </h3>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {item.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <footer className="border-t border-border-brand py-8 px-4">
        <p className="text-center text-sm text-text-secondary max-w-xl mx-auto">
          Prefer a bank transfer, or have a question about your donation? Contact us at{" "}
          <a href="mailto:vetsforfuturesl@gmail.com" className="text-[#EF9F27] hover:underline">
            vetsforfuturesl@gmail.com
          </a>{" "}
          or call{" "}
          <a href="tel:+94777226301" className="text-[#EF9F27] hover:underline">
            +94 77 722 6301
          </a>
          .
        </p>
      </footer>
    </div>
  );
}
