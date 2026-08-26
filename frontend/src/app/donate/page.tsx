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

const IMPACT_ITEMS = [
  {
    title: "Feeds a rescued animal for a week",
    /* TODO: replace with real VFF program copy */
    description: "Covers food and basic care for one animal in our shelter.",
  },
  {
    title: "Funds a vet visit",
    /* TODO: replace with real VFF program copy */
    description: "Pays for a check-up, vaccination, or minor treatment.",
  },
  {
    title: "Supports a rescue operation",
    /* TODO: replace with real VFF program copy */
    description: "Helps cover transport and equipment for animal rescues.",
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
      {/* Hero */}
      <section className="bg-bg-brand text-text-primary py-20 px-4">
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <Heart className="w-12 h-12 mx-auto text-accent" fill="currentColor" />
          <h1 className="text-4xl md:text-5xl font-bold font-heading">
            Help Us Protect Animals in Need
          </h1>
          <p className="text-lg text-text-secondary max-w-xl mx-auto">
            {/* TODO: replace with real VFF mission statement */}
            Vets For Future rescues, treats, and shelters animals across Sri
            Lanka. Every donation goes directly toward their care.
          </p>
        </div>
      </section>

      {/* Amount selector */}
      <section className="max-w-xl mx-auto px-4 -mt-10 mb-16">
        <Card className="bg-surface border-border-brand shadow-lg">
          <CardContent className="pt-6 space-y-6">
            <h2 className="text-xl font-semibold text-center">
              Make a Donation
            </h2>

            <div className="grid grid-cols-2 gap-3">
              {PRESET_AMOUNTS.map((preset) => (
                <Button
                  key={preset}
                  variant={selected === preset && !custom ? "default" : "outline"}
                  className={
                    selected === preset && !custom
                      ? "bg-accent text-bg-brand hover:bg-accent/90"
                      : ""
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
              className="w-full bg-accent text-bg-brand hover:bg-accent/90 gap-2"
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
            <Card key={item.title} className="bg-surface border-border-brand">
              <CardContent className="pt-6 space-y-2">
                <h3 className="font-semibold text-text-primary">
                  {item.title}
                </h3>
                <p className="text-sm text-text-secondary">
                  {item.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Footer note */}
      <footer className="border-t border-border-brand py-8 px-4">
        <p className="text-center text-sm text-text-secondary max-w-xl mx-auto">
          {/* TODO: replace with real contact details */}
          VFF is not yet able to process online payments directly. For bank
          transfer details, contact us at{" "}
          <a href="mailto:info@vff.example.org" className="underline">
            info@vff.example.org
          </a>
          .
        </p>
      </footer>

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Online Payments Coming Soon</DialogTitle>
            <DialogDescription>
              {/* TODO: replace with real contact details */}
              We're not yet able to process online donations directly. To
              donate {amount ? `LKR ${amount.toLocaleString()}` : ""}, please
              contact us at info@vff.example.org and we'll help you complete
              your gift.
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </div>
  );
}