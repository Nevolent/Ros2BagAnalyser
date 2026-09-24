import type { ReactNode } from 'react';
export const searchGroups: {
  label: string;
  items: { label: string; route: string; icon: ReactNode }[];
}[] = [
  {
    label: 'Platform',
    items: [
      {
        label: 'Recordings',
        route: 'recordings',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-layout-grid"
            aria-hidden="true"
          >
            <rect width="7" height="7" x="3" y="3" rx="1"></rect>
            <rect width="7" height="7" x="14" y="3" rx="1"></rect>
            <rect width="7" height="7" x="14" y="14" rx="1"></rect>
            <rect width="7" height="7" x="3" y="14" rx="1"></rect>
          </svg>
        ),
      },
      {
        label: 'Contacts',
        route: 'contacts',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-users"
            aria-hidden="true"
          >
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
            <path d="M16 3.128a4 4 0 0 1 0 7.744"></path>
            <path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>
            <circle cx="9" cy="7" r="4"></circle>
          </svg>
        ),
      },
      {
        label: 'Deals',
        route: 'deals',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-handshake"
            aria-hidden="true"
          >
            <path d="m11 17 2 2a1 1 0 1 0 3-3"></path>
            <path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"></path>
            <path d="m21 3 1 11h-2"></path>
            <path d="M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3"></path>
            <path d="M3 4h8"></path>
          </svg>
        ),
      },
      {
        label: 'Calendar',
        route: 'calendar',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-calendar-days"
            aria-hidden="true"
          >
            <path d="M8 2v3"></path>
            <path d="M16 2v3"></path>
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <path d="M3 9h18"></path>
            <path d="M8 13h.01"></path>
            <path d="M12 13h.01"></path>
            <path d="M16 13h.01"></path>
            <path d="M8 17h.01"></path>
            <path d="M12 17h.01"></path>
            <path d="M16 17h.01"></path>
          </svg>
        ),
      },
      {
        label: 'Processing',
        route: 'processing',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-chart-column"
            aria-hidden="true"
          >
            <path d="M3 3v16a2 2 0 0 0 2 2h16"></path>
            <path d="M18 17V9"></path>
            <path d="M13 17V5"></path>
            <path d="M8 17v-3"></path>
          </svg>
        ),
      },
      {
        label: 'Analysis',
        route: 'analysis',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-git-branch"
            aria-hidden="true"
          >
            <path d="M15 6a9 9 0 0 0-9 9V3"></path>
            <circle cx="18" cy="6" r="3"></circle>
            <circle cx="6" cy="18" r="3"></circle>
          </svg>
        ),
      },
    ],
  },
  {
    label: 'System',
    items: [
      {
        label: 'Settings',
        route: 'settings',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-settings"
            aria-hidden="true"
          >
            <path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
        ),
      },
    ],
  },
  {
    label: 'General',
    items: [
      {
        label: 'Help Center',
        route: 'help',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-circle-question-mark"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
            <path d="M12 17h.01"></path>
          </svg>
        ),
      },
      {
        label: 'Documentation',
        route: 'documentation',
        icon: (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="lucide lucide-book-open"
            aria-hidden="true"
          >
            <path d="M12 5v16"></path>
            <path d="M20.001 19A2 2 0 0022 17V5a2 2 0 00-1.999-2L16 3.002A5 5 0 0012 5a5 5 0 00-4-2H4a2 2 0 00-2 2v12a2 2 0 001.999 2H8a5 5 0 014 2 5 5 0 014-2z"></path>
          </svg>
        ),
      },
    ],
  },
];
