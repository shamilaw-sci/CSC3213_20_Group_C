'use client';

import { useEffect, useRef, useState } from 'react';

// Each section's reveal is independent and one-way (once visible, stays
// visible), so there's no need for a shared observer or a parent-level map —
// every section just owns its own ref and flag.
export function useScrollReveal<T extends HTMLElement = HTMLElement>() {
  const ref = useRef<T>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setRevealed(true);
      },
      { threshold: 0.15 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const revealClass = `transition-all duration-1000 ${
    revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
  }`;

  return { ref, revealed, revealClass };
}
