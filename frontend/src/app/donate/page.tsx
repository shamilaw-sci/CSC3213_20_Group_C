"use client";

import { useState } from "react";
import { Heart, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

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

export default function DonatePage() {
  const [selected, setSelected] = useState<number | null>(null);
  const [custom, setCustom] = useState("");
  const [showModal, setShowModal] = useState(false);

  const amount = custom ? Number(custom) : selected;
  const canDonate = !!amount && amount > 0;

  const donateUrl = process.env.NEXT_PUBLIC_DONATE_URL;

  const handleDonate = () => {
    if (!canDonate) return;
    if (donateUrl) {
      window.location.href = `${donateUrl}?amount=${amount}`;
    } else {
      setShowModal(true);
    }
  };

  return (
    <div className="min-h-screen bg-bg-subtle text-text-primary">
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
        </div>
      </section>

      {/* Amount selector */}
      <section className="max-w-xl mx-auto px-4 -mt-10 mb-16 relative">
        <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card">
          <CardContent className="pt-6 space-y-6">
            <h2 className="text-xl font-semibold text-center font-heading">
              Make a Donation
            </h2>

            <div className="grid grid-cols-2 gap-3">
              {PRESET_AMOUNTS.map((preset) => (
                <Button
                  key={preset}
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

            <div className="space-y-2">
              <label className="text-sm text-text-secondary">
                Or enter a custom amount (LKR)
              </label>
              <Input
                type="number"
                min={1}
                placeholder="e.g. 3000"
                value={custom}
                onChange={(e) => {
                  setCustom(e.target.value);
                  setSelected(null);
                }}
              />
            </div>

            <Button
              size="lg"
              disabled={!canDonate}
              onClick={handleDonate}
              className="w-full bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90 hover:scale-[1.02] shadow-lg shadow-amber-500/20 transition-all gap-2"
            >
              Donate {canDonate ? `LKR ${amount!.toLocaleString()}` : ""}
              <ArrowRight className="w-4 h-4" />
            </Button>
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

      {/* Footer note — VFF genuinely can't process online payments yet, so
          this stays an honest contact-us fallback, not a fake payment flow. */}
      <footer className="border-t border-border-brand py-8 px-4">
        <p className="text-center text-sm text-text-secondary max-w-xl mx-auto">
          VFF is not yet able to process online payments directly. For bank
          transfer details, contact us at{" "}
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

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Online Payments Coming Soon</DialogTitle>
            <DialogDescription>
              We&apos;re not yet able to process online donations directly. To
              donate {amount ? `LKR ${amount.toLocaleString()}` : ""}, please
              contact us at vetsforfuturesl@gmail.com or call +94 77 722 6301
              and we&apos;ll help you complete your gift.
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}
