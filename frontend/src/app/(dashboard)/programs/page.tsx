import { redirect } from 'next/navigation';

// Programs are split into lifecycle pages (Upcoming / Active / Completed).
// The old single page, and every link still pointing at it, lands on Active.
export default function ProgramsIndexPage() {
  redirect('/programs/active');
}
