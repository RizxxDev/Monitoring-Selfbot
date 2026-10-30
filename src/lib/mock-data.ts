import { Account, MetricHistory, EventLog } from './types';

export const INITIAL_MOCK_ACCOUNTS: Account[] = [
  {
    id: 'a101-bf89-4b11-9a2c-982141561001',
    label: 'Farmer-Alpha-01',
    encrypted_token: 'enc_eyJhbGciOiJBMjU2R0NNIn0.AlphaToken...',
    channel_id: '119283748291028374',
    farmable_item: "pot o' gems",
    gem_floor: 2000,
    status: 'ACTIVE',
    avatar_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=128&q=80',
    last_heartbeat: new Date().toISOString(),
    created_at: new Date(Date.now() - 7 * 86400000).toISOString(),
    updated_at: new Date().toISOString(),
    metrics: {
      gems_balance: 148200,
      stock_remaining: 42,
      is_farming: true,
      buff_clover_sec: 2450,    // ~40 min remaining
      buff_arroz_sec: 5320,     // ~1h 28min remaining
      buff_benedict_sec: 890,   // ~14 min remaining
      gateway_ping_ms: 48,
    },
  },
  {
    id: 'a102-bf89-4b11-9a2c-982141561002',
    label: 'Harvester-Beta-02',
    encrypted_token: 'enc_eyJhbGciOiJBMjU2R0NNIn0.BetaToken...',
    channel_id: '119283748291028375',
    farmable_item: 'laser grid',
    gem_floor: 3000,
    status: 'ACTIVE',
    avatar_url: 'https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?w=128&q=80',
    last_heartbeat: new Date().toISOString(),
    created_at: new Date(Date.now() - 5 * 86400000).toISOString(),
    updated_at: new Date().toISOString(),
    metrics: {
      gems_balance: 93450,
      stock_remaining: 18,
      is_farming: true,
      buff_clover_sec: 720,     // ~12 min remaining
      buff_arroz_sec: 180,      // ~3 min (warning low)
      buff_benedict_sec: 0,     // Expired!
      gateway_ping_ms: 62,
    },
  },
  {
    id: 'a103-bf89-4b11-9a2c-982141561003',
    label: 'Grow-Spender-03',
    encrypted_token: 'enc_eyJhbGciOiJBMjU2R0NNIn0.GammaToken...',
    channel_id: '119283748291028376',
    farmable_item: 'chandeliers',
    gem_floor: 1500,
    status: 'PAUSED',
    avatar_url: 'https://images.unsplash.com/photo-1614680376593-902f749f7ffc?w=128&q=80',
    last_heartbeat: new Date(Date.now() - 360000).toISOString(),
    created_at: new Date(Date.now() - 3 * 86400000).toISOString(),
    updated_at: new Date().toISOString(),
    metrics: {
      gems_balance: 312000,
      stock_remaining: 120,
      is_farming: false,
      buff_clover_sec: 0,
      buff_arroz_sec: 0,
      buff_benedict_sec: 0,
      gateway_ping_ms: 0,
    },
  },
  {
    id: 'a104-bf89-4b11-9a2c-982141561004',
    label: 'Night-Shift-04',
    encrypted_token: 'enc_eyJhbGciOiJBMjU2R0NNIn0.DeltaToken...',
    channel_id: '119283748291028377',
    farmable_item: "pot o' gems",
    gem_floor: 2000,
    status: 'ERROR',
    avatar_url: 'https://images.unsplash.com/photo-1563089145-599997674d42?w=128&q=80',
    last_heartbeat: new Date(Date.now() - 1200000).toISOString(),
    created_at: new Date(Date.now() - 2 * 86400000).toISOString(),
    updated_at: new Date().toISOString(),
    metrics: {
      gems_balance: 1840,
      stock_remaining: 0,
      is_farming: false,
      buff_clover_sec: 0,
      buff_arroz_sec: 0,
      buff_benedict_sec: 0,
      gateway_ping_ms: 0,
    },
  },
];

// Generate 24 hours of realistic metric history for an account
export function generateMockMetricsHistory(accountId: string, baseGems = 120000): MetricHistory[] {
  const points: MetricHistory[] = [];
  const now = Date.now();
  const stepMs = 60 * 60 * 1000; // hourly points (24 points)

  let currentGems = baseGems - 24 * 3200; // starting 24h ago
  for (let i = 24; i >= 0; i--) {
    const pointTime = new Date(now - i * stepMs).toISOString();
    // randomize hourly gain between 2500 and 4200
    const gain = Math.floor(Math.random() * 1700) + 2500;
    currentGems += gain;

    points.push({
      id: 1000 + i,
      account_id: accountId,
      timestamp: pointTime,
      gems_balance: currentGems,
      stock_remaining: Math.floor(Math.random() * 40) + 10,
      is_farming: true,
      buff_clover_sec: Math.floor(Math.random() * 3000),
      buff_arroz_sec: Math.floor(Math.random() * 6000),
      buff_benedict_sec: Math.floor(Math.random() * 1500),
      gateway_ping_ms: Math.floor(Math.random() * 30) + 40,
    });
  }
  return points;
}

export const INITIAL_MOCK_LOGS: EventLog[] = [
  {
    id: 901,
    account_id: 'a101-bf89-4b11-9a2c-982141561001',
    timestamp: new Date(Date.now() - 35000).toISOString(),
    event_type: 'ANTI_AFK_SOLVED',
    severity: 'INFO',
    message: 'Prompt verifikasi anti-AFK terdeteksi dan berhasil dijawab.',
    metadata: { latency_ms: 1420 },
  },
  {
    id: 902,
    account_id: 'a101-bf89-4b11-9a2c-982141561001',
    timestamp: new Date(Date.now() - 120000).toISOString(),
    event_type: 'BUFF_APPLIED',
    severity: 'INFO',
    message: 'Berhasil mengonsumsi Lucky Clover dari inventory (Buff diperbarui +60m).',
    metadata: { item_name: 'Lucky Clover' },
  },
  {
    id: 903,
    account_id: 'a102-bf89-4b11-9a2c-982141561002',
    timestamp: new Date(Date.now() - 240000).toISOString(),
    event_type: 'SHOP_PURCHASE',
    severity: 'INFO',
    message: 'Auto-restock 20x laser grid berhasil via toko in-game.',
    metadata: { item_name: 'laser grid', quantity: 20, cost: 4000 },
  },
  {
    id: 904,
    account_id: 'a104-bf89-4b11-9a2c-982141561004',
    timestamp: new Date(Date.now() - 1200000).toISOString(),
    event_type: 'ERROR',
    severity: 'CRITICAL',
    message: 'Gems berada di bawah batas Gem Floor (1,840 < 2,000). Restock otomatis terhenti untuk mencegah kehabisan saldo.',
    metadata: { error_code: 'INSUFFICIENT_GEMS_FLOOR' },
  },
  {
    id: 905,
    account_id: 'a102-bf89-4b11-9a2c-982141561002',
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    event_type: 'ANTI_AFK_SOLVED',
    severity: 'INFO',
    message: 'Prompt verifikasi anti-AFK terdeteksi dan berhasil dijawab.',
    metadata: { latency_ms: 980 },
  },
];
