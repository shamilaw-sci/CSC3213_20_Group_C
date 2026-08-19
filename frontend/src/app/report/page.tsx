// frontend/src/app/report/page.tsx
'use client';

import { useState } from 'react';
import { RescueCasesService } from '@/services/rescue-cases.service';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { ImagePlus, X } from 'lucide-react';
import LocationPicker from '@/components/heatmap/LocationPicker';

type Step = 'form' | 'locating' | 'confirm-location' | 'submitting';

export default function ReportCasePage() {
  const [step, setStep] = useState<Step>('form');
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
    const form = new FormData(e.currentTarget);
    setPendingFields({
      animal_type: form.get('animal_type') as string,
      description: (form.get('description') as string) || undefined,
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
      clearPhoto();
      setStep('form');
    } catch (err) {
      toast.error("Couldn't submit your report. Please try again.");
      setStep('confirm-location');
    }
  }

  return (
    <div className="min-h-screen bg-bg-brand text-text-primary p-6">
      <div className="max-w-lg mx-auto space-y-4 pt-16">
        <h1 className="text-xl font-semibold">Report an animal in need</h1>

        {step === 'form' && (
          <form onSubmit={handleFormSubmit} className="space-y-4">
            <select name="animal_type" required className="w-full border border-border-brand rounded-lg p-2 bg-surface">
              <option value="">Animal type</option>
              <option>Dog</option>
              <option>Cat</option>
              <option>Cow</option>
              <option>Other</option>
            </select>

            <textarea
              name="description"
              placeholder="What's the situation?"
              className="w-full border border-border-brand rounded-lg p-2 bg-surface"
              rows={4}
            />

            <div>
              {!photoPreview ? (
                <label
                  htmlFor="photo-upload"
                  className="flex flex-col items-center justify-center gap-2 w-full border border-dashed border-border-brand rounded-lg p-6 bg-surface cursor-pointer hover:border-[#EF9F27]/50 hover:bg-bg-subtle transition-colors text-text-secondary"
                >
                  <ImagePlus className="w-6 h-6" />
                  <span className="text-xs font-medium">Tap to add a photo</span>
                </label>
              ) : (
                <div className="relative w-full h-48 rounded-lg overflow-hidden border border-border-brand">
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

            <Button type="submit" className="w-full bg-[#EF9F27] text-white">
              Next: confirm location
            </Button>
          </form>
        )}

        {step === 'locating' && (
          <p className="text-text-secondary text-sm py-12 text-center">Getting your location...</p>
        )}

        {step === 'confirm-location' && coords && (
          <div className="space-y-4">
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
                className="flex-1 bg-[#EF9F27] text-white"
                onClick={handleFinalSubmit}
              >
                Confirm & submit
              </Button>
            </div>
          </div>
        )}

        {step === 'submitting' && (
          <p className="text-text-secondary text-sm py-12 text-center">Submitting report...</p>
        )}
      </div>
    </div>
  );
}