import HomeHeader from '@/components/home/HomeHeader';
import HeroSection from '@/components/home/HeroSection';
import StatsBand from '@/components/home/StatsBand';
import AboutSection from '@/components/home/AboutSection';
import ImpactSection from '@/components/home/ImpactSection';
import ProjectsSection from '@/components/home/ProjectsSection';
import ActivitySection from '@/components/home/ActivitySection';
import ContactSection from '@/components/home/ContactSection';
import HomeFooter from '@/components/home/HomeFooter';

export default function Homepage() {
  return (
    <div className="min-h-screen bg-bg-brand text-text-primary font-sans selection:bg-[#EF9F27]/30 overflow-x-hidden flex flex-col justify-between">
      <HomeHeader />

      <main className="flex-grow pt-16">
        <HeroSection />
        <StatsBand />
        <AboutSection />
        <ImpactSection />
        <ProjectsSection />
        <ActivitySection />
        <ContactSection />
      </main>

      <HomeFooter />
    </div>
  );
}
