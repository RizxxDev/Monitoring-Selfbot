export const DEFAULT_MASTER_PASSWORD = 'admin123';
export const AUTH_COOKIE_NAME = 'monitor_auth_session';

export const BUFF_CONFIG = {
  clover: {
    id: 'buff_clover_sec',
    name: 'Lucky Clover',
    shortName: 'Clover',
    maxSeconds: 3600, // 1 hour
    color: 'emerald',
    icon: '🍀',
  },
  arroz: {
    id: 'buff_arroz_sec',
    name: 'Arroz Con Pollo',
    shortName: 'Arroz',
    maxSeconds: 7200, // 2 hours
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
  "pot o' gems",
  'laser grid',
  'chandeliers',
  'pepper tree',
  'fish tank',
  'high tech block',
  'sorcerer stone',
];
