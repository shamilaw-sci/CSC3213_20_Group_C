'use client';

import { MapPin, Mail, Phone, Clock } from 'lucide-react';
import { useScrollReveal } from './useScrollReveal';

export default function ContactSection() {
  const { ref, revealClass } = useScrollReveal<HTMLElement>();

  return (
    <section
      id="contact"
      ref={ref}
      className={`bg-bg-subtle border-t border-border-brand py-20 ${revealClass}`}
    >
      <div className="max-w-[1280px] mx-auto px-6 md:px-12 grid grid-cols-1 lg:grid-cols-2 gap-12">
        <div className="space-y-6">
          <span className="text-xs font-bold tracking-wider text-text-secondary uppercase">
            ● Reach Our Teams
          </span>
          <h2 className="text-3xl font-bold tracking-tight font-heading">Kalubovila Operations Office</h2>
          <p className="text-text-secondary text-sm md:text-base leading-relaxed">
            Our central operations coordinates staff scheduling, payroll computations, and medical supply audits. Contact us for administrative inquiries.
          </p>

          <div className="space-y-4 pt-4">
            <div className="flex items-center gap-3 text-sm text-text-secondary">
              <MapPin size={18} className="text-[#EF9F27]" />
              <span>No. 02, Edward Place, Sri Sunandarama Mw, Kalubovila, Sri Lanka</span>
            </div>
            <div className="flex items-center gap-3 text-sm text-text-secondary">
              <Mail size={18} className="text-[#EF9F27]" />
              <span>vetsforfuturesl@gmail.com</span>
            </div>
            <div className="flex items-center gap-3 text-sm text-text-secondary">
              <Phone size={18} className="text-[#EF9F27]" />
              <span>+94 77 722 6301</span>
            </div>
          </div>
        </div>

        <div className="h-[280px] md:h-[320px] rounded-2xl overflow-hidden shadow-lg relative">
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{ backgroundImage: "url('/images/vff-team.jpg')" }}
          />
          {/* The badge below carries its own background, so the full-image
              scrim was pure dimming. */}
          <div className="absolute bottom-6 left-6 text-xs font-semibold text-text-primary bg-surface/90 backdrop-blur-sm py-2 px-3.5 rounded-lg shadow-card flex items-center gap-2">
            <Clock size={14} className="text-[#EF9F27]" /> Emergency response active
          </div>
        </div>
      </div>
    </section>
  );
}
