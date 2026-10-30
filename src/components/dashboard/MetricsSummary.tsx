'use client';

import React from 'react';
import { Play, Pause, Plus, Gem, Activity, Package, Wifi, Search, Filter } from 'lucide-react';
import { Account, AccountStatus } from '@/lib/types';
import { simulationStore } from '@/lib/simulation-store';
import { useToast } from './Toast';

interface MetricsSummaryProps {
  accounts: Account[];
  filterStatus: string;
  setFilterStatus: (status: string) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  onOpenAddModal: () => void;
}

export function MetricsSummary({
  accounts,
  filterStatus,
  setFilterStatus,
  searchQuery,
  setSearchQuery,
  onOpenAddModal,
}: MetricsSummaryProps) {
  const { showToast } = useToast();

  const totalGems = accounts.reduce((acc, a) => acc + (a.metrics?.gems_balance || 0), 0);
  const totalStock = accounts.reduce((acc, a) => acc + (a.metrics?.stock_remaining || 0), 0);
  const activeCount = accounts.filter((a) => a.status === 'ACTIVE').length;
  const pausedCount = accounts.filter((a) => a.status === 'PAUSED').length;
  const errorCount = accounts.filter((a) => a.status === 'ERROR').length;
  const avgPing = accounts.length > 0
    ? Math.round(
        accounts.reduce((acc, a) => acc + (a.metrics?.gateway_ping_ms || 0), 0) /
        accounts.filter((a) => a.status === 'ACTIVE').length || 0
      )
    : 0;

  const handleStartAll = () => {
    simulationStore.startAll();
    showToast({
      type: 'success',
      title: 'Perintah Massal: START ALL',
      message: 'Seluruh bot nonaktif dialihkan ke status ACTIVE.',
    });
  };

  const handlePauseAll = () => {
    simulationStore.pauseAll();
    showToast({
      type: 'warning',
      title: 'Perintah Massal: PAUSE ALL',
      message: 'Seluruh bot aktif telah dijeda (PAUSED).',
    });
  };

  return (
    <div className="space-y-6">
      {/* 4 Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* Total Gems */}
        <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-discord-blurple/30 transition shadow-lg">
          <div className="absolute top-0 right-0 w-24 h-24 bg-discord-blurple/10 rounded-full blur-2xl group-hover:bg-discord-blurple/20 transition"></div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Total Gems Farm</span>
            <div className="p-2 rounded-xl bg-discord-blurple/15 text-discord-blurple">
              <Gem className="w-4 h-4" />
            </div>
          </div>
          <div className="text-xl sm:text-2xl lg:text-3xl font-black text-white tracking-tight">
            {totalGems.toLocaleString()} <span className="text-sm font-semibold text-discord-blurple">💎</span>
          </div>
          <p className="text-[11px] text-gray-400 mt-1">Gabungan dari {accounts.length} akun terdaftar</p>
        </div>

        {/* Active Accounts */}
        <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-emerald-500/30 transition shadow-lg">
          <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full blur-2xl group-hover:bg-emerald-500/20 transition"></div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Status Worker</span>
            <div className="p-2 rounded-xl bg-emerald-500/15 text-emerald-400">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="text-xl sm:text-2xl lg:text-3xl font-black text-white tracking-tight flex items-baseline gap-2">
            <span>{activeCount}</span>
            <span className="text-xs font-medium text-gray-400">/ {accounts.length} Aktif</span>
          </div>
          <div className="flex items-center gap-2 mt-1 text-[11px]">
            <span className="text-emerald-400 font-medium">{activeCount} running</span>
            <span className="text-gray-500">•</span>
            <span className="text-amber-400 font-medium">{pausedCount} paused</span>
            {errorCount > 0 && (
              <>
                <span className="text-gray-500">•</span>
                <span className="text-rose-400 font-medium">{errorCount} error</span>
              </>
            )}
          </div>
        </div>

        {/* Total Stock */}
        <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-amber-500/30 transition shadow-lg">
          <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/10 rounded-full blur-2xl group-hover:bg-amber-500/20 transition"></div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Total Stok Farmable</span>
            <div className="p-2 rounded-xl bg-amber-500/15 text-amber-400">
              <Package className="w-4 h-4" />
            </div>
          </div>
          <div className="text-xl sm:text-2xl lg:text-3xl font-black text-white tracking-tight">
            {totalStock.toLocaleString()} <span className="text-sm font-semibold text-amber-400">item</span>
          </div>
          <p className="text-[11px] text-gray-400 mt-1">Sisa persediaan di tas bot</p>
        </div>

        {/* Gateway Ping */}
        <div className="bg-[#15161b] border border-white/5 rounded-2xl p-4 sm:p-5 relative overflow-hidden group hover:border-sky-500/30 transition shadow-lg">
          <div className="absolute top-0 right-0 w-24 h-24 bg-sky-500/10 rounded-full blur-2xl group-hover:bg-sky-500/20 transition"></div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Rata-rata Ping WSS</span>
            <div className="p-2 rounded-xl bg-sky-500/15 text-sky-400">
              <Wifi className="w-4 h-4" />
            </div>
          </div>
          <div className="text-xl sm:text-2xl lg:text-3xl font-black text-white tracking-tight flex items-baseline gap-1.5">
            <span>{avgPing}</span>
            <span className="text-sm font-semibold text-sky-400">ms</span>
          </div>
          <p className="text-[11px] text-gray-400 mt-1">Koneksi Discord Gateway aktif</p>
        </div>
      </div>

      {/* Action Toolbar & Filters */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 pt-2">
        {/* Search & Status Filter */}
        <div className="flex flex-wrap items-center gap-2.5 flex-1">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Cari label akun / channel..."
              className="w-full bg-[#16171d] border border-white/10 rounded-xl py-2 pl-9 pr-4 text-xs sm:text-sm text-white placeholder-gray-500 focus:outline-none focus:border-discord-blurple transition"
            />
          </div>

          <div className="flex items-center bg-[#16171d] border border-white/10 rounded-xl p-1 gap-1 text-xs">
            {['ALL', 'ACTIVE', 'PAUSED', 'ERROR'].map((st) => (
              <button
                key={st}
                onClick={() => setFilterStatus(st)}
                className={`px-3 py-1.5 rounded-lg font-medium transition ${
                  filterStatus === st
                    ? 'bg-discord-blurple text-white shadow-md'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>

        {/* Global Controls & Add Button */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleStartAll}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-semibold transition"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Start All</span>
          </button>

          <button
            onClick={handlePauseAll}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/30 text-xs font-semibold transition"
          >
            <Pause className="w-3.5 h-3.5 fill-current" />
            <span>Pause All</span>
          </button>

          <button
            onClick={onOpenAddModal}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-discord-blurple to-indigo-600 hover:from-discord-blurple/90 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-discord-blurple/20 transition"
          >
            <Plus className="w-4 h-4" />
            <span>Tambah Akun</span>
          </button>
        </div>
      </div>
    </div>
  );
}
