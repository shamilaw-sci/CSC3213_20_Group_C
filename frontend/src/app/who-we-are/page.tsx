import type { Metadata } from 'next';
import HomeHeader from '@/components/home/HomeHeader';
import HomeFooter from '@/components/home/HomeFooter';
import ClosingCTA from '@/components/home/ClosingCTA';
import WhoWeAreHero from '@/components/who-we-are/WhoWeAreHero';
import MissionStatement from '@/components/who-we-are/MissionStatement';
import StoryTimeline from '@/components/who-we-are/StoryTimeline';
import FoundersSection from '@/components/who-we-are/FoundersSection';
import ValuesSection from '@/components/who-we-are/ValuesSection';
import TrainingSection from '@/components/who-we-are/TrainingSection';

export const metadata: Metadata = {
  title: 'Who We Are | Vets For Future',
  description:
    "Vets For Future is Sri Lanka's first and only organization specializing in humane animal population control. Founded in 2000 by Dr. Chamith Nanayakkara and Dr. Udaya Wijayawardana.",
};

export default function WhoWeArePage() {
  return (
    <div className="min-h-screen bg-bg-brand text-text-primary font-sans selection:bg-[#EF9F27]/30 overflow-x-hidden flex flex-col justify-between">
      <HomeHeader />

      {/* Ordered so a visitor meets the organization before its credentials:
          who -> why -> how it got here -> who runs it -> what it believes ->
          how it scales -> what to do about it. */}
      <main className="flex-grow pt-16">
        <WhoWeAreHero />
        <MissionStatement />
        <StoryTimeline />
        <FoundersSection />
        <ValuesSection />
        <TrainingSection />
        <ClosingCTA />
      </main>

      <HomeFooter />
    </div>
  );
}
