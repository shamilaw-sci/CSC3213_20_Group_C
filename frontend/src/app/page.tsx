import HomeHeader from '@/components/home/HomeHeader';
import HeroSection from '@/components/home/HeroSection';
import UpcomingClinicsStrip from '@/components/home/UpcomingClinicsStrip';
import ProblemSection from '@/components/home/ProblemSection';
import StatsBand from '@/components/home/StatsBand';
import AboutSection from '@/components/home/AboutSection';
import ProgramsSection from '@/components/home/ProgramsSection';
import VisionBand from '@/components/home/VisionBand';
import ImpactSection from '@/components/home/ImpactSection';
import ProjectsSection from '@/components/home/ProjectsSection';
import ActivitySection from '@/components/home/ActivitySection';
import VideoSection from '@/components/home/VideoSection';
import ClosingCTA from '@/components/home/ClosingCTA';
import ContactSection from '@/components/home/ContactSection';
import HomeFooter from '@/components/home/HomeFooter';

export default function Homepage() {
  return (
    <div className="min-h-screen bg-bg-brand text-text-primary font-sans selection:bg-[#EF9F27]/30 overflow-x-hidden flex flex-col justify-between">
      <HomeHeader />

      {/* Ordered as a narrative: hook -> why it matters -> scale of the
          response -> who we are -> what we do -> what it achieved -> where
          -> what's happening now -> outside corroboration -> act. The
          clinics strip sits under the hook because it is the one thing a
          local visitor may need to act on this week; it is absent when
          nothing is published. */}
      <main className="flex-grow pt-16">
        <HeroSection />
        <UpcomingClinicsStrip />
        <ProblemSection />
        <StatsBand />
        <AboutSection />
        <ProgramsSection />
        <VisionBand />
        <ImpactSection />
        <ProjectsSection />
        <ActivitySection />
        <VideoSection />
        <ClosingCTA />
        <ContactSection />
      </main>

      <HomeFooter />
    </div>
  );
}
