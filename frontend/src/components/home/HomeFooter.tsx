'use client';

import { MapPin, Mail } from 'lucide-react';
import Link from 'next/link';
import Image from 'next/image';

export default function HomeFooter() {
  return (
    <footer className="border-t border-border-brand bg-bg-brand pt-16 pb-8 text-sm text-text-secondary">
      <div className="max-w-[1280px] mx-auto px-6 md:px-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 pb-12">
        <div className="space-y-4">
          <div className="flex items-center gap-2.5">
            <Image src="/images/vff-logo.png" alt="Vets For Future" width={32} height={32} className="h-8 w-8 object-contain" />
            <span className="text-base font-bold text-text-primary">Vets For Future</span>
          </div>
          <p className="leading-relaxed">
            Sri Lanka&apos;s first and only organization specializing in humane animal population control — working since 2000 toward a healthier coexistence between people and animals.
          </p>
        </div>
        <div className="space-y-4">
          <span className="font-bold uppercase tracking-wider text-text-primary">Take Action</span>
          <ul className="space-y-2">
            <li><Link href="/report" className="hover:text-text-primary">Report an Animal</Link></li>
            <li><Link href="/outbreak-map" className="hover:text-text-primary">Case Hotspot Map</Link></li>
          </ul>
        </div>
        <div className="space-y-4">
          <span className="font-bold uppercase tracking-wider text-text-primary">Our Work</span>
          <ul className="space-y-2">
            <li><Link href="/who-we-are" className="hover:text-text-primary">Who We Are</Link></li>
            <li>Sterilization & Vaccination</li>
            <li>Rabies Eradication</li>
            <li>Free Animal Health Clinics</li>
            <li>Community Awareness & Feeding</li>
            <li>Veterinary Training</li>
          </ul>
        </div>
        <div className="space-y-4">
          <span className="font-bold uppercase tracking-wider text-text-primary">Reach Us</span>
          <ul className="space-y-2">
            <li className="flex items-center gap-2"><MapPin size={14} /> Kalubovila, Sri Lanka</li>
            <li className="flex items-center gap-2"><Mail size={14} /> vetsforfuturesl@gmail.com</li>
          </ul>
        </div>
      </div>

      <div className="max-w-[1280px] mx-auto px-6 md:px-12 border-t border-border-brand/60 pt-6 flex flex-col md:flex-row justify-between items-center gap-4 text-text-secondary">
        <span>© {new Date().getFullYear()} Vets For Future. All Rights Reserved.</span>
        <Link href="/login" className="hover:text-text-primary transition-colors">
          VFF staff sign in
        </Link>
      </div>
    </footer>
  );
}
