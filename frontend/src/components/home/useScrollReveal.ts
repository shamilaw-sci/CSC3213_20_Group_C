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

    // Reveal is a progressive enhancement — content must never be left
    // permanently invisible because the API is missing.
    if (typeof IntersectionObserver === 'undefined') {
      setRevealed(true);
      return;
    }

    let fired = false;
    const observer = new IntersectionObserver(
      ([entry]) => {
        fired = true;
        if (entry.isIntersecting) setRevealed(true);
      },
      { threshold: 0.15 }
    );

    observer.observe(el);

    // IntersectionObserver delivers an initial callback for every observed
    // element regardless of whether it's on screen. If nothing arrives at
    // all, the API isn't actually functioning (some embedded/automated
    // browsers, aggressive privacy modes) — reveal rather than leave the
    // section blank forever. Checking "fired at all" rather than a blanket
    // timeout keeps the scroll animation intact in normal browsers.
    const guard = setTimeout(() => {
      if (!fired) setRevealed(true);
    }, 1500);

    return () => {
      observer.disconnect();
      clearTimeout(guard);
    };
  }, []);

  const revealClass = `transition-all duration-1000 ${
    revealed ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
  }`;

  return { ref, revealed, revealClass };
}
