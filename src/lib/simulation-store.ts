'use client';

import { Account, EventLog, BotCommand, CommandType } from './types';
import { INITIAL_MOCK_ACCOUNTS, INITIAL_MOCK_LOGS, generateMockMetricsHistory } from './mock-data';
import { BUFF_CONFIG } from './constants';

type Listener = () => void;

class SimulationStore {
  private accounts: Account[] = [];
  private logs: EventLog[] = [];
  private commands: BotCommand[] = [];
  private listeners: Set<Listener> = new Set();
  private timer: NodeJS.Timeout | null = null;
  private isClient = false;
  private nextLogId = 1000;
  private nextCommandId = 500;

  constructor() {
    this.accounts = JSON.parse(JSON.stringify(INITIAL_MOCK_ACCOUNTS));
    this.logs = JSON.parse(JSON.stringify(INITIAL_MOCK_LOGS));
  }

  public init() {
    if (this.isClient) return;
    this.isClient = true;

    // Load from localStorage if present
    if (typeof window !== 'undefined') {
      try {
        const storedAccounts = localStorage.getItem('gc_monitor_accounts');
        if (storedAccounts) {
          this.accounts = JSON.parse(storedAccounts);
        }
        const storedLogs = localStorage.getItem('gc_monitor_logs');
        if (storedLogs) {
          this.logs = JSON.parse(storedLogs);
        }
      } catch (e) {
        // Fallback to initial
      }
    }

    // Start 1-second simulation clock
    if (!this.timer) {
      this.timer = setInterval(() => {
        this.tick();
      }, 1000);
    }
  }

  private saveToStorage() {
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem('gc_monitor_accounts', JSON.stringify(this.accounts));
        localStorage.setItem('gc_monitor_logs', JSON.stringify(this.logs.slice(0, 100)));
      } catch (e) {
        // Storage full or quota exceeded
      }
    }
  }

  public subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify() {
    this.listeners.forEach((l) => l());
  }

  private tick() {
    let changed = false;
    const now = new Date();

    this.accounts = this.accounts.map((acc) => {
      if (acc.status !== 'ACTIVE' || !acc.metrics) return acc;

      changed = true;
      const m = { ...acc.metrics };

      // Decrement buff countdowns
      if (m.buff_clover_sec > 0) m.buff_clover_sec -= 1;
      if (m.buff_arroz_sec > 0) m.buff_arroz_sec -= 1;
      if (m.buff_benedict_sec > 0) m.buff_benedict_sec -= 1;

      // Increment gems periodically (approx 1-2 gems every 2-3 seconds ~ 2000/hr)
      if (Math.random() < 0.45) {
        m.gems_balance += Math.floor(Math.random() * 3) + 1;
      }

      // Decrement stock occasionally and simulate consumption
      if (Math.random() < 0.03 && m.stock_remaining > 0) {
        m.stock_remaining -= 1;
        // If stock hits 0, auto-restock simulation
        if (m.stock_remaining === 0 && m.gems_balance > acc.gem_floor + 2000) {
          m.stock_remaining += 20;
          m.gems_balance -= 2000;
          this.addEventLog({
            account_id: acc.id,
            event_type: 'SHOP_PURCHASE',
            severity: 'INFO',
            message: `Auto-restock 20x ${acc.farmable_item} berhasil diproses oleh bot.`,
            metadata: { item_name: acc.farmable_item, quantity: 20, cost: 2000 },
          });
        }
      }

      // Slightly fluctuate ping
      if (Math.random() < 0.1) {
        m.gateway_ping_ms = Math.max(28, Math.min(120, m.gateway_ping_ms + (Math.floor(Math.random() * 7) - 3)));
      }

      // Random anti-AFK event every ~60 seconds
      if (Math.random() < 0.012) {
        const latency = (Math.random() * 0.8 + 0.9).toFixed(2);
        this.addEventLog({
          account_id: acc.id,
          event_type: 'ANTI_AFK_SOLVED',
          severity: 'INFO',
          message: `Verifikasi anti-AFK berhasil diselesaikan via interaksi tombol (Latensi: ${latency}s).`,
          metadata: { latency_ms: Math.round(parseFloat(latency) * 1000) },
        });
      }

      return {
        ...acc,
        last_heartbeat: now.toISOString(),
        metrics: m,
      };
    });

    if (changed) {
      this.notify();
      this.saveToStorage();
    }
  }

  public getAccounts(): Account[] {
    return this.accounts;
  }

  public getAccountById(id: string): Account | undefined {
    return this.accounts.find((a) => a.id === id);
  }

  public getLogs(accountId?: string): EventLog[] {
    if (!accountId) return this.logs;
    return this.logs.filter((l) => l.account_id === accountId);
  }

  public addEventLog(log: Omit<EventLog, 'id' | 'timestamp'>) {
    const newLog: EventLog = {
      ...log,
      id: ++this.nextLogId,
      timestamp: new Date().toISOString(),
    };
    this.logs.unshift(newLog);
    if (this.logs.length > 200) {
      this.logs.pop();
    }
    this.notify();
    this.saveToStorage();
  }

  // Remote Actions
  public dispatchCommand(accountId: string, command: CommandType, payload?: Record<string, unknown>): BotCommand {
    const account = this.getAccountById(accountId);
    const newCommand: BotCommand = {
      id: ++this.nextCommandId,
      account_id: accountId,
      command,
      payload,
      status: 'EXECUTED',
      created_at: new Date().toISOString(),
      executed_at: new Date().toISOString(),
    };

    this.commands.unshift(newCommand);

    if (account) {
      if (command === 'START') {
        account.status = 'ACTIVE';
        if (account.metrics) account.metrics.is_farming = true;
        this.addEventLog({
          account_id: accountId,
          event_type: 'SYSTEM',
          severity: 'INFO',
          message: `Bot '${account.label}' dimulai (Status: ACTIVE).`,
        });
      } else if (command === 'PAUSE') {
        account.status = 'PAUSED';
        if (account.metrics) account.metrics.is_farming = false;
        this.addEventLog({
          account_id: accountId,
          event_type: 'SYSTEM',
          severity: 'WARNING',
          message: `Bot '${account.label}' dijeda oleh pengguna (Status: PAUSED).`,
        });
      } else if (command === 'FORCE_REBUFF') {
        if (account.metrics) {
          account.metrics.buff_clover_sec = BUFF_CONFIG.clover.maxSeconds;
          account.metrics.buff_arroz_sec = BUFF_CONFIG.arroz.maxSeconds;
          account.metrics.buff_benedict_sec = BUFF_CONFIG.benedict.maxSeconds;
        }
        this.addEventLog({
          account_id: accountId,
          event_type: 'BUFF_APPLIED',
          severity: 'INFO',
          message: `Force Re-buff berhasil dijalankan! Seluruh buff (Clover, Arroz, Benedict) telah diisi penuh.`,
        });
      } else if (command === 'FORCE_RESTOCK') {
        if (account.metrics) {
          account.metrics.stock_remaining += 20;
          account.metrics.gems_balance = Math.max(0, account.metrics.gems_balance - 2000);
        }
        this.addEventLog({
          account_id: accountId,
          event_type: 'SHOP_PURCHASE',
          severity: 'INFO',
          message: `Force Restock: Berhasil membeli 20x ${account.farmable_item} di toko in-game.`,
          metadata: { item_name: account.farmable_item, quantity: 20, cost: 2000 },
        });
      }
    }

    this.notify();
    this.saveToStorage();
    return newCommand;
  }

  public startAll() {
    this.accounts = this.accounts.map((a) => {
      if (a.status === 'PAUSED' || a.status === 'OFFLINE') {
        if (a.metrics) a.metrics.is_farming = true;
        return { ...a, status: 'ACTIVE' as const };
      }
      return a;
    });
    this.addEventLog({
      account_id: this.accounts[0]?.id || 'system',
      event_type: 'SYSTEM',
      severity: 'INFO',
      message: 'Perintah massal: Seluruh akun bot diaktifkan (START ALL).',
    });
    this.notify();
    this.saveToStorage();
  }

  public pauseAll() {
    this.accounts = this.accounts.map((a) => {
      if (a.status === 'ACTIVE') {
        if (a.metrics) a.metrics.is_farming = false;
        return { ...a, status: 'PAUSED' as const };
      }
      return a;
    });
    this.addEventLog({
      account_id: this.accounts[0]?.id || 'system',
      event_type: 'SYSTEM',
      severity: 'WARNING',
      message: 'Perintah massal: Seluruh akun bot dijeda (PAUSE ALL).',
    });
    this.notify();
    this.saveToStorage();
  }

  public addAccount(accountData: Omit<Account, 'id' | 'created_at' | 'updated_at' | 'last_heartbeat'>): Account {
    const newAcc: Account = {
      ...accountData,
      id: 'acc-' + Math.random().toString(36).substring(2, 9),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      last_heartbeat: new Date().toISOString(),
      metrics: accountData.metrics || {
        gems_balance: 5000,
        stock_remaining: 20,
        is_farming: true,
        buff_clover_sec: 3600,
        buff_arroz_sec: 7200,
        buff_benedict_sec: 1800,
        gateway_ping_ms: 55,
      },
    };
    this.accounts.unshift(newAcc);
    this.addEventLog({
      account_id: newAcc.id,
      event_type: 'SYSTEM',
      severity: 'INFO',
      message: `Akun baru '${newAcc.label}' berhasil ditambahkan ke dashboard.`,
    });
    this.notify();
    this.saveToStorage();
    return newAcc;
  }

  public updateAccount(id: string, updates: Partial<Account>): Account | undefined {
    const idx = this.accounts.findIndex((a) => a.id === id);
    if (idx === -1) return undefined;
    this.accounts[idx] = {
      ...this.accounts[idx],
      ...updates,
      updated_at: new Date().toISOString(),
    };
    this.addEventLog({
      account_id: id,
      event_type: 'SYSTEM',
      severity: 'INFO',
      message: `Konfigurasi akun '${this.accounts[idx].label}' diperbarui.`,
    });
    this.notify();
    this.saveToStorage();
    return this.accounts[idx];
  }

  public deleteAccount(id: string): boolean {
    const acc = this.getAccountById(id);
    this.accounts = this.accounts.filter((a) => a.id !== id);
    if (acc) {
      this.addEventLog({
        account_id: id,
        event_type: 'SYSTEM',
        severity: 'WARNING',
        message: `Akun '${acc.label}' dihapus dari monitoring.`,
      });
    }
    this.notify();
    this.saveToStorage();
    return true;
  }

  public resetToDefault() {
    this.accounts = JSON.parse(JSON.stringify(INITIAL_MOCK_ACCOUNTS));
    this.logs = JSON.parse(JSON.stringify(INITIAL_MOCK_LOGS));
    this.notify();
    this.saveToStorage();
  }
}

// Singleton simulation store instance
export const simulationStore = new SimulationStore();
