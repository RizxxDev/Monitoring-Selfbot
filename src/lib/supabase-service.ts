import { supabase, isSupabaseConfigured } from './supabase';
import { Account, BotCommand, CommandType, EventLog, MetricHistory } from './types';

export class SupabaseDataService {
  public static isEnabled(): boolean {
    return isSupabaseConfigured && supabase !== null;
  }

  public static async getAccounts(): Promise<Account[]> {
    if (!supabase) return [];
    
    // Fetch accounts
    const { data: accountsData, error: accError } = await supabase
      .from('accounts')
      .select('*')
      .order('created_at', { ascending: false });

    if (accError || !accountsData) {
      console.error('Failed to fetch accounts:', accError);
      return [];
    }

    // For each account, fetch latest metric
    const accountsWithMetrics: Account[] = await Promise.all(
      accountsData.map(async (acc) => {
        const { data: metricData } = await supabase!
          .from('metrics_history')
          .select('*')
          .eq('account_id', acc.id)
          .gt('gems_balance', 0)
          .order('timestamp', { ascending: false })
          .limit(1)
          .maybeSingle();

        return {
          id: acc.id,
          label: acc.label,
          encrypted_token: acc.encrypted_token,
          channel_id: acc.channel_id,
          farmable_item: acc.farmable_item,
          gem_floor: acc.gem_floor,
          status: acc.status,
          avatar_url: acc.avatar_url,
          last_heartbeat: acc.last_heartbeat,
          created_at: acc.created_at,
          updated_at: acc.updated_at,
          metrics: metricData
            ? {
                gems_balance: metricData.gems_balance,
                stock_remaining: metricData.stock_remaining,
                is_farming: metricData.is_farming,
                buff_clover_sec: metricData.buff_clover_sec,
                buff_arroz_sec: metricData.buff_arroz_sec,
                buff_benedict_sec: metricData.buff_benedict_sec,
                gateway_ping_ms: metricData.gateway_ping_ms,
              }
            : {
                gems_balance: 0,
                stock_remaining: 0,
                is_farming: acc.status === 'ACTIVE',
                buff_clover_sec: 0,
                buff_arroz_sec: 0,
                buff_benedict_sec: 0,
                gateway_ping_ms: 0,
              },
        };
      })
    );

    return accountsWithMetrics;
  }

  public static async getAccountById(id: string): Promise<Account | null> {
    if (!supabase) return null;
    const { data: acc, error } = await supabase
      .from('accounts')
      .select('*')
      .eq('id', id)
      .maybeSingle();

    if (error || !acc) return null;

    const { data: metricData } = await supabase
      .from('metrics_history')
      .select('*')
      .eq('account_id', id)
      .gt('gems_balance', 0)
      .order('timestamp', { ascending: false })
      .limit(1)
      .maybeSingle();

    return {
      ...acc,
      metrics: metricData
        ? {
            gems_balance: metricData.gems_balance,
            stock_remaining: metricData.stock_remaining,
            is_farming: metricData.is_farming,
            buff_clover_sec: metricData.buff_clover_sec,
            buff_arroz_sec: metricData.buff_arroz_sec,
            buff_benedict_sec: metricData.buff_benedict_sec,
            gateway_ping_ms: metricData.gateway_ping_ms,
          }
        : undefined,
    };
  }

  public static async addAccount(data: {
    label: string;
    encrypted_token: string;
    channel_id: string;
    farmable_item: string;
    gem_floor: number;
    avatar_url?: string;
  }): Promise<Account | null> {
    if (!supabase) return null;
    const { data: inserted, error } = await supabase
      .from('accounts')
      .insert({
        label: data.label,
        encrypted_token: data.encrypted_token,
        channel_id: data.channel_id,
        farmable_item: data.farmable_item,
        gem_floor: data.gem_floor,
        avatar_url: data.avatar_url,
        status: 'ACTIVE',
      })
      .select()
      .single();

    if (error) {
      console.error('Error inserting account:', error);
      throw error;
    }
    return inserted;
  }

  public static async updateAccount(id: string, updates: Partial<Account>): Promise<boolean> {
    if (!supabase) return false;
    const { error } = await supabase
      .from('accounts')
      .update({
        ...updates,
        updated_at: new Date().toISOString(),
      })
      .eq('id', id);

    return !error;
  }

  public static async deleteAccount(id: string): Promise<boolean> {
    if (!supabase) return false;
    const { error } = await supabase.from('accounts').delete().eq('id', id);
    return !error;
  }

  public static async dispatchCommand(
    accountId: string,
    command: CommandType,
    payload: Record<string, unknown> = {}
  ): Promise<BotCommand | null> {
    if (!supabase) return null;
    const { data, error } = await supabase
      .from('bot_commands')
      .insert({
        account_id: accountId,
        command,
        payload,
        status: 'PENDING',
      })
      .select()
      .single();

    if (error) {
      console.error('Error dispatching command:', error);
      throw error;
    }
    return data;
  }

  public static async getMetricsHistory(accountId: string): Promise<MetricHistory[]> {
    if (!supabase) return [];
    const { data, error } = await supabase
      .from('metrics_history')
      .select('*')
      .eq('account_id', accountId)
      .gt('gems_balance', 0)
      .order('timestamp', { ascending: true })
      .limit(100);

    if (error || !data) return [];
    return data;
  }

  public static async getEventLogs(accountId?: string): Promise<EventLog[]> {
    if (!supabase) return [];
    let query = supabase.from('event_logs').select('*').order('timestamp', { ascending: false }).limit(100);
    if (accountId) {
      query = query.eq('account_id', accountId);
    }
    const { data, error } = await query;
    if (error || !data) return [];
    return data;
  }

  public static subscribeRealtime(onTableChange: () => void) {
    if (!supabase) return () => {};

    const channel = supabase
      .channel('monitoring_realtime_changes')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'accounts' },
        () => onTableChange()
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'bot_commands' },
        () => onTableChange()
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'event_logs' },
        () => onTableChange()
      )
      .subscribe();

    return () => {
      supabase?.removeChannel(channel);
    };
  }
}
