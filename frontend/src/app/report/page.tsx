// frontend/src/app/report/page.tsx
'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import { ImagePlus, X, Loader2, MapPin, CheckCircle2, PawPrint } from 'lucide-react';
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
      {/* Full-bleed hero in the same shape as the donate page: photo, dark
          gradient, centred heading, and the form card floated up over the
          bottom edge. rescue-report.png stays at its natural 2.45:1 aspect
          rather than being bg-cover cropped like donate-hero.jpg, because it
          is a four-panel collage — cropping it top and bottom clips the
          animals in every panel. */}
      <section className="relative bg-[#0B0D12] overflow-hidden">
        <Image
          src="/images/rescue-report.png"
          alt="Animals cared for by Vets For Future"
          width={1984}
          height={809}
          priority
          className="w-full h-auto"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-black/10" />

        {/* Overlaid on the photo from md up, where the strip is tall enough to
            hold it. On phones the strip renders only ~160px tall, so the text
            sits below it against the section's dark background instead. */}
        <div className="relative md:absolute md:inset-x-0 md:bottom-0 max-w-3xl mx-auto px-4 flex flex-col items-center text-center space-y-4 pt-8 pb-16 md:pb-14">
          <PawPrint className="w-10 h-10 text-[#EF9F27]" />
          <h1 className="text-3xl md:text-5xl font-bold font-heading text-white tracking-tight">
            Report an animal in need
          </h1>
          <p className="text-sm md:text-lg text-white/85 max-w-xl leading-relaxed">
            Takes about a minute — we&apos;ll use your location to find them.
          </p>
        </div>
      </section>

      <section className="max-w-lg mx-auto px-4 -mt-10 mb-16 relative">
        <Card className="bg-surface border-border-brand/50 rounded-2xl shadow-card">
          <CardContent className="pt-6 space-y-6">
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
            )}

            {step === 'locating' && (
              <div className="py-8 flex flex-col items-center gap-3 text-center">
                <Loader2 className="w-6 h-6 text-[#EF9F27] animate-spin" />
                <p className="text-text-secondary text-sm">Getting your location...</p>
              </div>
            )}

            {step === 'confirm-location' && coords && (
              <div className="space-y-4">
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
              </div>
            )}

            {step === 'submitting' && (
              <div className="py-8 flex flex-col items-center gap-3 text-center">
                <Loader2 className="w-6 h-6 text-[#EF9F27] animate-spin" />
                <p className="text-text-secondary text-sm">Submitting report...</p>
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
