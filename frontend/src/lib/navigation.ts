import { 
  LayoutDashboard, 
  Users, 
  DollarSign, 
  Package,
  Calendar,
  Wallet,
  FileText,
  Boxes,
  RotateCcw,
  BookOpen,
  FolderOpen,
  MapPin,
  ClipboardList,
  Navigation,
  HeartHandshake,
  CalendarClock,
  CalendarDays,
  Plane,
  CalendarPlus,
  CircleCheckBig,
  HandCoins,
  ReceiptText
} from 'lucide-react';

import { hasAnyPermission, type Permission } from './permissions';

export interface NavItem {
  label: string;
  href: string;
  icon?: any;
  // A list means any of them.
  requiredPermission?: Permission | Permission[];
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

// The one visibility rule for the sidebar, shared with navigation.test.ts so
// the test checks the real logic rather than a copy of it.
export function canSeeNavItem(role: string, item: NavItem): boolean {
  return !item.requiredPermission || hasAnyPermission(role, item.requiredPermission);
}

export const NAVIGATION_CONFIG: NavSection[] = [
  {
    title: 'GENERAL',
    items: [
      { label: 'Overview', href: '/dashboard', icon: LayoutDashboard },
    ]
  },
  {
    title: 'HUMAN RESOURCES',
    items: [
      { label: 'Employees', href: '/hr/employees', icon: Users, requiredPermission: 'hr:manage' },
      // Director reads the monthly grid (hr:attendance:read); HR also edits.
      { label: 'Attendance', href: '/hr/attendance', icon: Calendar, requiredPermission: ['hr:attendance:manage', 'hr:attendance:read'] },
      // Attendance managers read it; editing inside needs hr:manage.
      { label: 'Schedules & Holidays', href: '/hr/schedules', icon: CalendarDays, requiredPermission: ['hr:manage', 'hr:attendance:manage'] },
      { label: 'Leave', href: '/hr/leave', icon: Plane, requiredPermission: 'leave:approve' },
      // Generate or approve: Director signs payroll off from this page.
      { label: 'Payroll', href: '/hr/payroll', icon: Wallet, requiredPermission: ['payroll:generate', 'payroll:approve'] },
    ]
  },
  {
    title: 'FINANCE',
    items: [
      { label: 'Overview', href: '/finance/overview', icon: DollarSign, requiredPermission: 'finance:read' },
      // finance:read, not write: the Ledger is the full record, so Director
      // reads it too. Adding, editing and voiding stay behind finance:write
      // inside the page.
      { label: 'Ledger', href: '/finance/ledger', icon: FileText, requiredPermission: 'finance:read' },
      { label: 'Reports', href: '/finance/reports', icon: FileText, requiredPermission: 'finance:read' },
    ]
  },
  {
    title: 'INVENTORY',
    items: [
      { label: 'Stock', href: '/inventory/stock', icon: Package, requiredPermission: 'inventory:read' },
      { label: 'Issue', href: '/inventory/issue', icon: Boxes, requiredPermission: 'inventory:issue' },
      { label: 'Returns', href: '/inventory/returns', icon: RotateCcw, requiredPermission: 'inventory:issue' },
    ]
  },
  {
    title: 'PROGRAMS',
    items: [
      // Programs move Upcoming -> Active -> Completed; one page per stage.
      { label: 'Upcoming Programs', href: '/programs/upcoming', icon: CalendarPlus, requiredPermission: 'programs:read' },
      { label: 'Active Programs', href: '/programs/active', icon: FolderOpen, requiredPermission: 'programs:read' },
      { label: 'Completed Programs', href: '/programs/completed', icon: CircleCheckBig, requiredPermission: 'programs:read' },
    ]
  },
  {
    // Both gated on volunteers:read, which no role holds without also holding
    // approve or assign. The pages themselves gate the mutating controls
    // separately, so a Director sees the roster and the rota but no Assign
    // button, and an Operations Lead sees no Approve button.
    title: 'VOLUNTEERS',
    items: [
      { label: 'Applications', href: '/volunteers', icon: HeartHandshake, requiredPermission: 'volunteers:read' },
      { label: 'Shifts', href: '/volunteers/shifts', icon: CalendarClock, requiredPermission: 'volunteers:read' },
    ]
  },
  {
    // Donations from the public donate page. finance:read, because every paid
    // donation is ledger income and the page shows donor contact details.
    title: 'DONATIONS',
    items: [
      { label: 'Donation details', href: '/donations', icon: HandCoins, requiredPermission: 'finance:read' },
    ]
  },
  {
  title: 'RESCUE CASES',
  items: [
    { label: 'Case Hotspots', href: '/cases', icon: MapPin, requiredPermission: 'rescue:read' },
    { label: 'Case Triage', href: '/case-triage', icon: ClipboardList, requiredPermission: 'rescue:read' },
    { label: 'Field Dispatch', href: '/dispatch', icon: Navigation, requiredPermission: 'rescue:read' },
  ]
  },
  {
    title: 'SELF SERVICE',
    items: [
      { label: 'My Attendance', href: '/me/attendance', icon: BookOpen, requiredPermission: 'hr:attendance:self' },
      { label: 'My Leave', href: '/me/leave', icon: Plane, requiredPermission: 'hr:attendance:self' },
      { label: 'My Payslips', href: '/me/payslips', icon: ReceiptText, requiredPermission: 'hr:attendance:self' },
    ]
  },
  {
    title: 'MANAGEMENT',
    items: [
      { label: 'System Admin', href: '/admin', icon: Users, requiredPermission: 'admin:users' }
    ]
  },
  {
    title: 'PERSONAL',
    items: [
      { label: 'Go to Website Home', href: '/', icon: LayoutDashboard },
      { label: 'Edit Profile', href: '/profile', icon: Users },
      { label: 'Account Settings', href: '/settings', icon: Wallet },
      { label: 'Support', href: '/support', icon: FileText },
    ]
  }
];
