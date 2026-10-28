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
  CalendarClock
} from 'lucide-react';

import type { Permission } from './permissions';

export interface NavItem {
  label: string;
  href: string;
  icon?: any;
  requiredPermission?: Permission;
}

export interface NavSection {
  title: string;
  items: NavItem[];
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
      { label: 'Attendance', href: '/hr/attendance', icon: Calendar, requiredPermission: 'hr:attendance:manage' },
      { label: 'Payroll', href: '/hr/payroll', icon: Wallet, requiredPermission: 'payroll:generate' },
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
      { label: 'Active Programs', href: '/programs', icon: FolderOpen, requiredPermission: 'programs:read' },
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
    // Both gated on volunteers:read, which no role holds without also holding
    // approve or assign. The pages themselves gate the mutating controls
    // separately, so a Director sees the roster and the rota but no Assign
    // button, and an Operations Lead sees no Approve button.
    title: 'VOLUNTEERS',
    items: [
      { label: 'Roster', href: '/volunteers', icon: HeartHandshake, requiredPermission: 'volunteers:read' },
      { label: 'Shifts', href: '/volunteers/shifts', icon: CalendarClock, requiredPermission: 'volunteers:read' },
    ]
  },
  {
    title: 'SELF SERVICE',
    items: [
      { label: 'My Attendance', href: '/me/attendance', icon: BookOpen, requiredPermission: 'hr:attendance:self' },
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
