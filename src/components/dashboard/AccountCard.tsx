'use client';

import React from 'react';
import Link from 'next/link';
import { Play, Pause, Sparkles, ShoppingBag, Eye, ExternalLink, Hash, Clock, AlertCircle } from 'lucide-react';
import { Account } from '@/lib/types';
import { BuffIndicator } from './BuffIndicator';
import { simulationStore } from '@/lib/simulation-store';
import { useToast } from './Toast';

interface AccountCardProps {
  account: Account;
  onOpenDrawer: (account: Account) => void;
}

export function AccountCard({ account, onOpenDrawer }: AccountCardProps) {
  const { showToast } = useToast();
  const m = account.metrics;

  const isRunning = account.status === 'ACTIVE';
  const isPaused = account.status === 'PAUSED';
  const isError = account.status === 'ERROR';

  const handleToggleStartPause = () => {
    if (isRunning) {
      simulationStore.dispatchCommand(account.id, 'PAUSE');
      showToast({
        type: 'warning',
        title: `Bot Dijeda: ${account.label}`,
        message: 'Perintah PAUSE telah dikirim ke worker.',
      });
    } else {
      simulationStore.dispatchCommand(account.id, 'START');
      showToast({
        type: 'success',
        title: `Bot Dijalankan: ${account.label}`,
        message: 'Perintah START telah dikirim ke worker.',
      });
    }
  };

  const handleForceRebuff = () => {
    simulationStore.dispatchCommand(account.id, 'FORCE_REBUFF');
    showToast({
      type: 'success',
      title: `Force Re-buff: ${account.label}`,
      message: 'Perintah konsumsi Clover, Arroz & Benedict berhasil diproses.',
    });
  };

  const handleForceRestock = () => {
    simulationStore.dispatchCommand(account.id, 'FORCE_RESTOCK');
    showToast({
      type: 'info',
      title: `Force Restock: ${account.label}`,
      message: `Membeli 20x ${account.farmable_item} di toko...`,
    });
  };

  // Heartbeat time string
  const getHeartbeatDisplay = () => {
    if (!account.last_heartbeat) return 'Belum ada ping';
    const diffSec = Math.floor((Date.now() - new Date(account.last_heartbeat).getTime()) / 1000);
    if (diffSec < 10) return 'Online (Baru saja)';
    if (diffSec < 60) return `${diffSec}d lalu`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m lalu`;
    return `${Math.floor(diffMin / 60)}j lalu`;
  };

  return (
    <div className="bg-[#15161b] border border-white/5 hover:border-discord-blurple/40 transition-all duration-200 rounded-2xl p-5 flex flex-col justify-between shadow-xl relative overflow-hidden group">
      {/* Top ambient highlight on active */}
      {isRunning && (
        <div className="absolute -top-12 -right-12 w-28 h-28 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none"></div>
      )}
      {isError && (
        <div className="absolute -top-12 -right-12 w-28 h-28 bg-rose-500/10 rounded-full blur-2xl pointer-events-none"></div>
      )}

      {/* Header: Avatar, Name, Status Badge */}
      <div>
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-3">
            <div className="relative">
              {account.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={account.avatar_url}
                  alt={account.label}
                  className="w-11 h-11 rounded-xl object-cover border border-white/10"
                />
              ) : (
                <div className="w-11 h-11 rounded-xl bg-[#202227] border border-white/10 flex items-center justify-center font-bold text-white text-base">
                  {account.label.charAt(0).toUpperCase()}
                </div>
              )}
              {/* Status Dot */}
              <span
                className={`absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full border-2 border-[#15161b] ${
                  isRunning
                    ? 'bg-emerald-500 animate-pulse'
                    : isPaused
                    ? 'bg-amber-400'
                    : 'bg-rose-500'
                }`}
              />
            </div>

            <div>
              <h3 className="font-bold text-white text-base leading-tight group-hover:text-discord-blurple transition flex items-center gap-2">
                <span>{account.label}</span>
              </h3>
              <p className="text-[11px] text-gray-400 flex items-center gap-1 mt-0.5 font-mono">
                <Hash className="w-3 h-3 text-gray-500" />
                <span className="truncate max-w-[140px]">{account.channel_id}</span>
              </p>
            </div>
          </div>

          {/* Status Badge */}
          <div className="flex items-center">
            {isRunning && (
              <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                RUNNING
              </span>
            )}
            {isPaused && (
              <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                PAUSED
              </span>
            )}
            {isError && (
              <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                ERROR
              </span>
            )}
          </div>
        </div>

        {/* Gems & Stock Data */}
        <div className="grid grid-cols-2 gap-2 mb-4 p-3 bg-[#101115] rounded-xl border border-white/5">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium uppercase text-gray-400 tracking-wider">Saldo Gems</span>
              {m && m.gems_balance > 0 && !isRunning && (
                <span className="text-[9px] text-gray-500 font-medium">Tersimpan</span>
              )}
            </div>
            <div className="text-lg font-extrabold text-white tracking-tight flex items-center gap-1 mt-0.5">
              <span>{m && m.gems_balance > 0 ? m.gems_balance.toLocaleString() : 'Menghubungkan...'}</span>
              <span className="text-xs text-discord-blurple">💎</span>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-medium uppercase text-gray-400 tracking-wider">Stok Farmable</span>
              <span className="text-[9px] text-gray-500 font-medium truncate max-w-[60px]">{getHeartbeatDisplay()}</span>
            </div>
            <div className="text-lg font-extrabold text-white tracking-tight flex items-baseline gap-1 mt-0.5">
              <span>{m ? m.stock_remaining : 0}</span>
              <span className="text-[11px] font-medium text-amber-400 truncate max-w-[80px]">
                {account.farmable_item}
              </span>
            </div>
          </div>
        </div>

        {/* 3 Buff Countdown Indicators */}
        <div className="space-y-1.5 mb-4">
          <div className="flex justify-between items-center text-[10px] uppercase tracking-wider text-gray-400 px-1 font-semibold">
            <span>Status 3 Buff Utama</span>
            <span>Countdown</span>
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            <BuffIndicator type="clover" secondsRemaining={m?.buff_clover_sec ?? 0} />
            <BuffIndicator type="arroz" secondsRemaining={m?.buff_arroz_sec ?? 0} />
            <BuffIndicator type="benedict" secondsRemaining={m?.buff_benedict_sec ?? 0} />
          </div>
        </div>

        {/* Heartbeat Footer */}
        <div className="flex items-center justify-between text-[11px] text-gray-400 py-1.5 border-t border-white/5 mb-4">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3 text-gray-500" />
            <span>Heartbeat: {getHeartbeatDisplay()}</span>
          </span>
          {m?.gateway_ping_ms ? (
            <span className="font-mono text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
              {m.gateway_ping_ms}ms
            </span>
          ) : (
            <span className="font-mono text-[10px] text-gray-500">Offline</span>
          )}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="space-y-2">
        {/* Quick Remote Action Row */}
        <div className="grid grid-cols-3 gap-1.5">
          <button
            onClick={handleToggleStartPause}
            className={`py-2 px-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 border transition ${
              isRunning
                ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border-amber-500/30'
                : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
            }`}
          >
            {isRunning ? (
              <>
                <Pause className="w-3.5 h-3.5 fill-current" />
                <span>Pause</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Start</span>
              </>
            )}
          </button>

          <button
            onClick={handleForceRebuff}
            className="py-2 px-2 rounded-xl text-xs font-semibold bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center justify-center gap-1 transition"
            title="Paksa makan buff clover, arroz, dan benedict"
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span>Re-buff</span>
          </button>

          <button
            onClick={handleForceRestock}
            className="py-2 px-2 rounded-xl text-xs font-semibold bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center justify-center gap-1 transition"
            title="Paksa beli stok item di toko in-game"
          >
            <ShoppingBag className="w-3.5 h-3.5 text-amber-400" />
            <span>Restock</span>
          </button>
        </div>

        {/* Inspection & Dedicated Page Links */}
        <div className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() => onOpenDrawer(account)}
            className="py-2 px-3 rounded-xl text-xs font-medium bg-[#1e2026] hover:bg-[#2b2d34] text-gray-300 hover:text-white border border-white/5 flex items-center justify-center gap-1.5 transition"
          >
            <Eye className="w-3.5 h-3.5 text-gray-400" />
            <span>Quick View</span>
          </button>

          <Link
            href={`/accounts/${account.id}`}
            className="py-2 px-3 rounded-xl text-xs font-medium bg-[#1e2026] hover:bg-discord-blurple hover:text-white text-gray-300 border border-white/5 flex items-center justify-center gap-1.5 transition"
          >
            <span>Analisis Penuh</span>
            <ExternalLink className="w-3 h-3 opacity-70" />
          </Link>
        </div>
      </div>
    </div>
  );
}
