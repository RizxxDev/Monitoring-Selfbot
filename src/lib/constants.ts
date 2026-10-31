export const DEFAULT_MASTER_PASSWORD = 'admin123';
export const AUTH_COOKIE_NAME = 'monitor_auth_session';

export const BUFF_CONFIG = {
  clover: {
    id: 'buff_clover_sec',
    name: 'Lucky Clover',
    shortName: 'Clover',
    maxSeconds: 1800, // 30 minutes
    color: 'emerald',
    icon: '🍀',
  },
  arroz: {
    id: 'buff_arroz_sec',
    name: 'Arroz Con Pollo',
    shortName: 'Arroz',
    maxSeconds: 1800, // 30 minutes
    color: 'amber',
    icon: '🍗',
  },
  benedict: {
    id: 'buff_benedict_sec',
    name: 'Eggs Benedict',
    shortName: 'Benedict',
    maxSeconds: 1800, // 30 minutes
    color: 'sky',
    icon: '🍳',
  },
} as const;

export const FARMABLE_ITEMS = [
  "Pot O' Gems",
  'Crystal Block',
  'Game Grave',
  'Rich Crystal',
  'Diamond Ore',
  'Diamond Block',
  'Void Crystal Ore',
];
