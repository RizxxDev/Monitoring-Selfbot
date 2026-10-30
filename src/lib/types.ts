export type AccountStatus = 'ACTIVE' | 'PAUSED' | 'ERROR' | 'OFFLINE' | 'CONNECTING';

export type CommandType = 'START' | 'PAUSE' | 'FORCE_REBUFF' | 'FORCE_RESTOCK';

export type CommandStatus = 'PENDING' | 'EXECUTED' | 'FAILED';

export type EventSeverity = 'INFO' | 'WARNING' | 'CRITICAL';

export type EventCategory = 'ANTI_AFK' | 'BUFF' | 'SHOP' | 'ERROR' | 'SYSTEM';

export interface Account {
  id: string;
  label: string;
  encrypted_token: string;
  channel_id: string;
  farmable_item: string;
  gem_floor: number;
  status: AccountStatus;
  avatar_url?: string;
  last_heartbeat: string;
  created_at: string;
  updated_at: string;
  // Dynamic runtime metrics attached for dashboard convenience
  metrics?: {
    gems_balance: number;
    stock_remaining: number;
    is_farming: boolean;
    buff_clover_sec: number;   // Lucky Clover (Max: 3600s / 1 hr)
    buff_arroz_sec: number;    // Arroz Con Pollo (Max: 7200s / 2 hr)
    buff_benedict_sec: number; // Eggs Benedict (Max: 1800s / 30 min)
    gateway_ping_ms: number;
  };
}

export interface BotCommand {
  id: number;
  account_id: string;
  command: CommandType;
  payload?: Record<string, unknown>;
  status: CommandStatus;
  created_at: string;
  executed_at?: string;
}

export interface MetricHistory {
  id: number;
  account_id: string;
  timestamp: string;
  gems_balance: number;
  stock_remaining: number;
  is_farming: boolean;
  buff_clover_sec: number;
  buff_arroz_sec: number;
  buff_benedict_sec: number;
  gateway_ping_ms: number;
}

export interface EventLog {
  id: number;
  account_id: string;
  timestamp: string;
  event_type: string;
  severity: EventSeverity;
  message: string;
  metadata?: {
    latency_ms?: number;
    item_name?: string;
    quantity?: number;
    cost?: number;
    error_code?: string;
    details?: string;
    [key: string]: unknown;
  };
}

export interface GlobalSummary {
  totalAccounts: number;
  activeAccounts: number;
  pausedAccounts: number;
  errorAccounts: number;
  totalGems: number;
  totalStock: number;
  averagePing: number;
}
