// frontend/src/app/report/page.tsx
'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { ImagePlus, X, Loader2, MapPin, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import Image from 'next/image';

const LocationPicker = dynamic(() => import('@/components/heatmap/LocationPicker'), { ssr: false });

type Step = 'form' | 'locating' | 'confirm-location' | 'submitting';

const ANIMAL_TYPES = ['Dog', 'Cat', 'Cow', 'Other'];

const STEPS: { key: Exclude<Step, 'locating' | 'submitting'> | 'confirm-location'; label: string }[] = [
  { key: 'form', label: 'Details' },
  { key: 'confirm-location', label: 'Location' },
];

export default function ReportCasePage() {
  const [step, setStep] = useState<Step>('form');
  const [animalType, setAnimalType] = useState('');
  const [description, setDescription] = useState('');
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [pendingFields, setPendingFields] = useState<{ animal_type: string; description?: string } | null>(null);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);

  function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoFile(file);
    setPhotoPreview(URL.createObjectURL(file));
  }

  function clearPhoto() {
    setPhotoFile(null);
    setPhotoPreview(null);
  }

  async function handleFormSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    // animal_type moved to controlled state to use the shared Select
    // component, which isn't a native form element — so the `required`
    // native-select behaviour has to be re-checked explicitly here.
    if (!animalType) {
      toast.error('Please select an animal type.');
      return;
    }

    setPendingFields({
      animal_type: animalType,
      description: description || undefined,
    });

    setStep('locating');
    const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 })
    ).catch(() => null);

    if (!pos) {
      toast.error("Couldn't get your location. Please enable location access and try again.");
      setStep('form');
      return;
    }

    setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
    setStep('confirm-location');
  }

  async function handleFinalSubmit() {
    if (!pendingFields || !coords) return;
    setStep('submitting');

    try {
      let photo_url: string | undefined;
      if (photoFile) {
        photo_url = await RescueCasesService.uploadPhoto(photoFile);
      }

      await RescueCasesService.createCase({
        animal_type: pendingFields.animal_type,
        description: pendingFields.description,
        lat: coords.lat,
        lng: coords.lng,
        photo_url,
      });

      toast.success('Report submitted — thank you for helping!');
      setPendingFields(null);
      setCoords(null);
      setAnimalType('');
      setDescription('');
      clearPhoto();
      setStep('form');
    } catch (err) {
      toast.error("Couldn't submit your report. Please try again.");
      setStep('confirm-location');
    }
  }

  const currentStepIndex = step === 'form' || step === 'locating' ? 0 : 1;

  return (
    <div className="min-h-screen bg-bg-subtle text-text-primary">
      <div className="max-w-5xl mx-auto px-6 pt-10 pb-16 space-y-8">
        {/* Banner with the heading overlaid. rescue-report.png is a 2.45:1
            horizontal strip, so it's rendered at its own aspect rather than
            forced into a fixed-height box — that keeps all four panels intact
            instead of trimming the animals top and bottom. next/image keeps
            the multi-MB PNG from being shipped raw. */}
        <div className="relative rounded-2xl overflow-hidden shadow-card border border-border-brand/50">
          <Image
            src="/images/rescue-report.png"
            alt="Animals cared for by Vets For Future"
            width={1984}
            height={809}
            priority
            className="w-full h-auto"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent" />
          <div className="absolute bottom-0 left-0 right-0 p-6 md:p-8">
            <h1 className="text-2xl md:text-4xl font-bold font-heading text-white tracking-tight drop-shadow">
              Report an animal in need
            </h1>
            <p className="text-xs md:text-base text-white/85 mt-1.5">
              Takes about a minute — we&apos;ll use your location to find them.
            </p>
          </div>
        </div>

        <div className="max-w-lg mx-auto space-y-6">
        {/* Step indicator */}
        <div className="flex items-center gap-2 px-1">
          {STEPS.map((s, i) => (
            <div key={s.key} className="flex items-center gap-2 flex-1 last:flex-none">
              <div
                className={cn(
                  'flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider',
                  i <= currentStepIndex ? 'text-[#EF9F27]' : 'text-text-muted'
                )}
              >
                <span
                  className={cn(
                    'w-5 h-5 rounded-full flex items-center justify-center text-[10px] shrink-0',
                    i < currentStepIndex
                      ? 'bg-[#EF9F27] text-white'
                      : i === currentStepIndex
                      ? 'border-2 border-[#EF9F27] text-[#EF9F27]'
                      : 'border border-border-brand text-text-muted'
                  )}
                >
                  {i < currentStepIndex ? <CheckCircle2 size={12} /> : i + 1}
                </span>
                {s.label}
              </div>
              {i < STEPS.length - 1 && (
                <div className={cn('h-px flex-1', i < currentStepIndex ? 'bg-[#EF9F27]' : 'bg-border-brand')} />
              )}
            </div>
          ))}
        </div>

        {step === 'form' && (
          <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card p-6">
            <form onSubmit={handleFormSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                  Animal type
                </label>
                <Select value={animalType} onValueChange={(val) => { if (typeof val === 'string') setAnimalType(val); }}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select an animal type" />
                  </SelectTrigger>
                  <SelectContent>
                    {ANIMAL_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>{type}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                  What&apos;s the situation? <span className="text-text-muted normal-case font-normal">(optional)</span>
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. injured leg, looks unwell, stuck somewhere..."
                  className="w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm text-text-primary transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  rows={4}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                  Photo <span className="text-text-muted normal-case font-normal">(optional)</span>
                </label>
                {!photoPreview ? (
                  <label
                    htmlFor="photo-upload"
                    className="flex flex-col items-center justify-center gap-2 w-full border-2 border-dashed border-border-brand rounded-xl p-8 bg-bg-subtle cursor-pointer hover:border-[#EF9F27]/50 hover:bg-bg-subtle/70 transition-colors text-text-secondary"
                  >
                    <ImagePlus className="w-6 h-6" />
                    <span className="text-xs font-medium">Tap to add a photo</span>
                  </label>
                ) : (
                  <div className="relative w-full h-48 rounded-xl overflow-hidden border border-border-brand">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={photoPreview} alt="Preview" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={clearPhoto}
                      className="absolute top-2 right-2 bg-black/60 hover:bg-black/80 text-white rounded-full p-1.5 transition-colors"
                      aria-label="Remove photo"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
                <input
                  id="photo-upload"
                  type="file"
                  name="photo"
                  accept="image/jpeg,image/png,image/webp"
                  capture="environment"
                  onChange={handlePhotoChange}
                  className="hidden"
                />
              </div>

              <Button
                type="submit"
                className="w-full bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90 hover:scale-[1.02] shadow-lg shadow-amber-500/20 transition-all"
              >
                Next: confirm location
              </Button>
            </form>
          </Card>
        )}

        {step === 'locating' && (
          <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card p-10 flex flex-col items-center gap-3 text-center">
            <Loader2 className="w-6 h-6 text-[#EF9F27] animate-spin" />
            <p className="text-text-secondary text-sm">Getting your location...</p>
          </Card>
        )}

        {step === 'confirm-location' && coords && (
          <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card p-6 space-y-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
              <MapPin className="w-4 h-4 text-[#EF9F27]" />
              Drag the pin if this isn&apos;t quite right
            </div>
            <LocationPicker
              initialLat={coords.lat}
              initialLng={coords.lng}
              onChange={(lat, lng) => setCoords({ lat, lng })}
            />
            <div className="flex gap-3">
              <Button
                type="button"
                variant="outline"
                className="flex-1"
                onClick={() => setStep('form')}
              >
                Back
              </Button>
              <Button
                type="button"
                className="flex-1 bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90"
                onClick={handleFinalSubmit}
              >
                Confirm & submit
              </Button>
            </div>
          </Card>
        )}

        {step === 'submitting' && (
          <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card p-10 flex flex-col items-center gap-3 text-center">
            <Loader2 className="w-6 h-6 text-[#EF9F27] animate-spin" />
            <p className="text-text-secondary text-sm">Submitting report...</p>
          </Card>
        )}
        </div>
      </div>
    </div>
  );
}
