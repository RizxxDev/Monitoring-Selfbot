'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Bot,
  Play,
  Pause,
  Sparkles,
  ShoppingBag,
  Activity,
  Shield,
  Save,
  Clock,
  Hash,
  Filter,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  HelpCircle,
} from 'lucide-react';
import { Account, EventLog, MetricHistory } from '@/lib/types';
import { FARMABLE_ITEMS } from '@/lib/constants';
import { simulationStore } from '@/lib/simulation-store';
import { generateMockMetricsHistory } from '@/lib/mock-data';
import { BuffIndicator } from '@/components/dashboard/BuffIndicator';
import { GemsTimeSeriesChart } from '@/components/charts/GemsTimeSeriesChart';
import { Header } from '@/components/dashboard/Header';
import { ToastProvider, useToast } from '@/components/dashboard/Toast';

export default function AccountDetailPageWrapper() {
  return (
    <ToastProvider>
      <AccountDetailPage />
    </ToastProvider>
  );
}

function AccountDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { showToast } = useToast();
  const accountId = params?.id as string;

  const [account, setAccount] = useState<Account | null>(null);
  const [metricsHistory, setMetricsHistory] = useState<MetricHistory[]>([]);
  const [logs, setLogs] = useState<EventLog[]>([]);
  const [logCategory, setLogCategory] = useState<string>('ALL');

  // Form states
  const [label, setLabel] = useState('');
  const [channelId, setChannelId] = useState('');
  const [farmableItem, setFarmableItem] = useState('');
  const [gemFloor, setGemFloor] = useState<number>(2000);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    simulationStore.init();

    const loadData = () => {
      const acc = simulationStore.getAccountById(accountId);
      if (acc) {
        setAccount(acc);
        setLabel(acc.label);
        setChannelId(acc.channel_id);
        setFarmableItem(acc.farmable_item);
        setGemFloor(acc.gem_floor);
        setLogs(simulationStore.getLogs(accountId));
      }
    };

    loadData();
    // Generate initial historical points for the chart
    setMetricsHistory(generateMockMetricsHistory(accountId, 140000));

    const unsubscribe = simulationStore.subscribe(() => {
      loadData();
    });

    return () => unsubscribe();
  }, [accountId]);

  if (!account) {
    return (
      <div className="min-h-screen bg-[#0e0f14] flex flex-col">
        <Header />
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center space-y-4">
          <div className="p-4 rounded-2xl bg-white/5 text-gray-400">
            <Bot className="w-10 h-10" />
          </div>
          <h2 className="text-xl font-bold text-white">Akun Tidak Ditemukan</h2>
          <p className="text-xs text-gray-400 max-w-sm">
            Akun bot dengan ID tersebut tidak ditemukan di sistem monitoring.
          </p>
          <Link
            href="/"
            className="px-4 py-2.5 rounded-xl bg-discord-blurple text-white text-xs font-semibold hover:bg-discord-blurple/90 transition flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Kembali ke Dashboard</span>
          </Link>
        </div>
      </div>
    );
  }

  const m = account.metrics;
  const isRunning = account.status === 'ACTIVE';

  const handleToggleStartPause = () => {
    if (isRunning) {
      simulationStore.dispatchCommand(account.id, 'PAUSE');
      showToast({ type: 'warning', title: 'Bot Dijeda', message: 'Status diubah ke PAUSED.' });
    } else {
      simulationStore.dispatchCommand(account.id, 'START');
      showToast({ type: 'success', title: 'Bot Dijalankan', message: 'Status diubah ke ACTIVE.' });
    }
  };

  const handleForceRebuff = () => {
    simulationStore.dispatchCommand(account.id, 'FORCE_REBUFF');
    showToast({ type: 'success', title: 'Re-buff Sukses', message: 'Seluruh buff bot telah diisi penuh.' });
  };

  const handleForceRestock = () => {
    simulationStore.dispatchCommand(account.id, 'FORCE_RESTOCK');
    showToast({ type: 'info', title: 'Restock Terkirim', message: `Membeli 20x ${account.farmable_item}.` });
  };

  const handleSaveConfig = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    simulationStore.updateAccount(account.id, {
      label,
      channel_id: channelId,
      farmable_item: farmableItem,
      gem_floor: Number(gemFloor),
    });
    setIsSaving(false);
    showToast({
      type: 'success',
      title: 'Pengaturan Disimpan',
      message: 'Konfigurasi akun berhasil diperbarui.',
    });
  };

  // Filter logs by category
  const filteredLogs = logs.filter((log) => {
    if (logCategory === 'ALL') return true;
    return log.event_type.startsWith(logCategory);
  });

  return (
    <div className="min-h-screen bg-[#0e0f14] text-[#e0e2e8] flex flex-col selection:bg-discord-blurple selection:text-white">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Top Breadcrumb & Quick Action Row */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-white/5">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="p-2.5 rounded-xl bg-[#16171d] hover:bg-[#20222a] border border-white/5 text-gray-400 hover:text-white transition"
              title="Kembali ke Dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>

            <div className="flex items-center gap-3">
              {account.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={account.avatar_url}
                  alt={account.label}
                  className="w-11 h-11 rounded-xl object-cover border border-white/10"
                />
              ) : (
                <div className="w-11 h-11 rounded-xl bg-discord-blurple/20 text-discord-blurple border border-discord-blurple/30 flex items-center justify-center font-bold">
                  {account.label.charAt(0)}
                </div>
              )}

              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold text-white tracking-tight">{account.label}</h1>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${
                      isRunning
                        ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                        : account.status === 'PAUSED'
                        ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                        : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                    }`}
                  >
                    {account.status}
                  </span>
                </div>
                <p className="text-xs text-gray-400 flex items-center gap-1 font-mono mt-0.5">
                  <Hash className="w-3 h-3 text-gray-500" />
                  <span>Channel: {account.channel_id}</span>
                </p>
              </div>
            </div>
          </div>

          {/* Quick Remote Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleToggleStartPause}
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 border transition ${
                isRunning
                  ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border-amber-500/30'
                  : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
              }`}
            >
              {isRunning ? <Pause className="w-3.5 h-3.5 fill-current" /> : <Play className="w-3.5 h-3.5 fill-current" />}
              <span>{isRunning ? 'Jeda Bot' : 'Jalankan'}</span>
            </button>

            <button
              onClick={handleForceRebuff}
              className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center gap-1.5 transition"
            >
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              <span>Force Re-buff</span>
            </button>

            <button
              onClick={handleForceRestock}
              className="px-3.5 py-2 rounded-xl text-xs font-semibold bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1.5 transition"
            >
              <ShoppingBag className="w-3.5 h-3.5 text-amber-400" />
              <span>Force Restock</span>
            </button>
          </div>
        </div>

        {/* Real-time Status & Buff Row */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4">
            <span className="text-[11px] text-gray-400 uppercase font-medium">Saldo Gems Saat Ini</span>
            <div className="text-2xl font-black text-white mt-1">
              {m?.gems_balance.toLocaleString()} 💎
            </div>
            <p className="text-[10px] text-gray-500 mt-1">Batas aman floor: {account.gem_floor.toLocaleString()}</p>
          </div>

          <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4">
            <span className="text-[11px] text-gray-400 uppercase font-medium">Sisa Stok Tas</span>
            <div className="text-2xl font-black text-amber-400 mt-1">
              {m?.stock_remaining} pcs
            </div>
            <p className="text-[10px] text-gray-500 mt-1 capitalize">Item: {account.farmable_item}</p>
          </div>

          <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4">
            <span className="text-[11px] text-gray-400 uppercase font-medium">Gateway Ping</span>
            <div className="text-2xl font-black text-sky-400 mt-1">
              {m?.gateway_ping_ms ?? 0} ms
            </div>
            <p className="text-[10px] text-gray-500 mt-1">Status WSS: Normal</p>
          </div>

          <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4">
            <span className="text-[11px] text-gray-400 uppercase font-medium">Auto-Farm Engine</span>
            <div className="text-2xl font-black text-emerald-400 mt-1 flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-gray-500'}`} />
              <span>{isRunning ? 'ACTIVE' : 'IDLE'}</span>
            </div>
            <p className="text-[10px] text-gray-500 mt-1">Multi-task asyncio loop</p>
          </div>
        </div>

        {/* 3 Buff Status Cards */}
        <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-300">
              Durasi Buff Aktif (Countdown Real-Time)
            </h3>
            <span className="text-[11px] text-gray-500">Auto Re-buff triggered ketika timer habis</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <BuffIndicator type="clover" secondsRemaining={m?.buff_clover_sec ?? 0} />
            <BuffIndicator type="arroz" secondsRemaining={m?.buff_arroz_sec ?? 0} />
            <BuffIndicator type="benedict" secondsRemaining={m?.buff_benedict_sec ?? 0} />
          </div>
        </div>

        {/* Time Series Chart */}
        <GemsTimeSeriesChart data={metricsHistory} accountLabel={account.label} />

        {/* Split Section: Config Form & Audit Event Logs */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Form Konfigurasi (1 col) */}
          <div className="bg-[#15161b] border border-white/5 rounded-2xl p-5 space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Shield className="w-4 h-4 text-discord-blurple" />
              <span>Konfigurasi Operasional</span>
            </h3>

            <form onSubmit={handleSaveConfig} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-gray-300 block mb-1">
                  Nama / Label Akun
                </label>
                <input
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  className="w-full bg-[#101115] border border-white/10 rounded-xl px-3.5 py-2 text-xs text-white focus:outline-none focus:border-discord-blurple"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-300 block mb-1">
                  Channel ID / Thread ID
                </label>
                <input
                  type="text"
                  value={channelId}
                  onChange={(e) => setChannelId(e.target.value)}
                  className="w-full bg-[#101115] border border-white/10 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-discord-blurple"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-300 block mb-1">
                  Target Farmable Item
                </label>
                <select
                  value={farmableItem}
                  onChange={(e) => setFarmableItem(e.target.value)}
                  className="w-full bg-[#101115] border border-white/10 rounded-xl px-3 py-2 text-xs text-white capitalize focus:outline-none focus:border-discord-blurple"
                >
                  {FARMABLE_ITEMS.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-300 block mb-1">
                  Gem Floor (Minimal Saldo)
                </label>
                <input
                  type="number"
                  value={gemFloor}
                  onChange={(e) => setGemFloor(Number(e.target.value))}
                  min={0}
                  step={500}
                  className="w-full bg-[#101115] border border-white/10 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-discord-blurple"
                  required
                />
                <span className="text-[10px] text-gray-500 block mt-1">
                  Bot akan menghentikan pembelian jika gems menyentuh batas ini.
                </span>
              </div>

              <button
                type="submit"
                disabled={isSaving}
                className="w-full bg-gradient-to-r from-discord-blurple to-indigo-600 hover:from-discord-blurple/90 hover:to-indigo-500 text-white text-xs font-semibold py-2.5 rounded-xl shadow-lg shadow-discord-blurple/20 flex items-center justify-center gap-2 transition"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Simpan Perubahan</span>
              </button>
            </form>
          </div>

          {/* Audit Event Log Table (2 cols) */}
          <div className="lg:col-span-2 bg-[#15161b] border border-white/5 rounded-2xl p-5 flex flex-col justify-between space-y-4">
            <div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Activity className="w-4 h-4 text-discord-blurple" />
                  <span>Audit Event Log & Anti-AFK Tracker</span>
                </h3>

                {/* Filter Category */}
                <div className="flex items-center gap-1 bg-[#101115] border border-white/5 rounded-xl p-1 text-[11px]">
                  {['ALL', 'ANTI_AFK', 'BUFF', 'SHOP', 'ERROR'].map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setLogCategory(cat)}
                      className={`px-2.5 py-1 rounded-lg font-medium transition ${
                        logCategory === cat
                          ? 'bg-discord-blurple text-white'
                          : 'text-gray-400 hover:text-white'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              {/* Logs Table / List */}
              <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                {filteredLogs.length === 0 ? (
                  <div className="p-8 text-center text-xs text-gray-500">
                    Tidak ada event log yang sesuai dengan filter.
                  </div>
                ) : (
                  filteredLogs.map((log) => (
                    <div
                      key={log.id}
                      className="p-3 bg-[#111216] border border-white/5 rounded-xl text-xs space-y-1 hover:border-white/10 transition"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                              log.severity === 'CRITICAL'
                                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                : log.severity === 'WARNING'
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            }`}
                          >
                            {log.event_type}
                          </span>
                          {log.metadata?.latency_ms && (
                            <span className="text-[10px] text-sky-400 font-mono">
                              ⚡ {(Number(log.metadata.latency_ms) / 1000).toFixed(2)}s latensi
                            </span>
                          )}
                        </div>
                        <span className="text-[10px] text-gray-500 font-mono">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-gray-300 text-xs leading-relaxed">{log.message}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="pt-2 border-t border-white/5 flex items-center justify-between text-[11px] text-gray-500">
              <span>Menampilkan {filteredLogs.length} kejadian</span>
              <span className="text-emerald-400">Stream realtime aktif</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
