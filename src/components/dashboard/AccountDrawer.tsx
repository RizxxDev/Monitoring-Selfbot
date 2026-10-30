'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { X, ExternalLink, Save, Trash2, Shield, Activity, Hash, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Account, EventLog } from '@/lib/types';
import { FARMABLE_ITEMS } from '@/lib/constants';
import { simulationStore } from '@/lib/simulation-store';
import { useToast } from './Toast';

interface AccountDrawerProps {
  account: Account | null;
  isOpen: boolean;
  onClose: () => void;
}

export function AccountDrawer({ account, isOpen, onClose }: AccountDrawerProps) {
  const { showToast } = useToast();

  const [label, setLabel] = useState('');
  const [channelId, setChannelId] = useState('');
  const [farmableItem, setFarmableItem] = useState('');
  const [gemFloor, setGemFloor] = useState<number>(2000);
  const [recentLogs, setRecentLogs] = useState<EventLog[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (account) {
      setLabel(account.label);
      setChannelId(account.channel_id);
      setFarmableItem(account.farmable_item);
      setGemFloor(account.gem_floor);
      setRecentLogs(simulationStore.getLogs(account.id).slice(0, 5));
    }
  }, [account]);

  if (!isOpen || !account) return null;

  const handleSave = (e: React.FormEvent) => {
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
      title: 'Konfigurasi Disimpan',
      message: `Perubahan pengaturan '${label}' berhasil diperbarui.`,
    });
    onClose();
  };

  const handleDelete = () => {
    if (confirm(`Yakin ingin menghapus akun '${account.label}' dari dashboard monitoring?`)) {
      simulationStore.deleteAccount(account.id);
      showToast({
        type: 'warning',
        title: 'Akun Dihapus',
        message: `Akun '${account.label}' telah dikeluarkan dari daftar monitoring.`,
      });
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity animate-fadeIn"
      />

      {/* Drawer content */}
      <div className="relative w-full max-w-md bg-[#131419] border-l border-white/10 h-full flex flex-col z-10 shadow-2xl overflow-y-auto">
        {/* Drawer Header */}
        <div className="p-6 border-b border-white/10 flex items-center justify-between sticky top-0 bg-[#131419]/90 backdrop-blur-md z-20">
          <div className="flex items-center gap-3">
            {account.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={account.avatar_url}
                alt={account.label}
                className="w-10 h-10 rounded-xl object-cover border border-white/10"
              />
            ) : (
              <div className="w-10 h-10 rounded-xl bg-discord-blurple/20 text-discord-blurple border border-discord-blurple/30 flex items-center justify-center font-bold">
                {account.label.charAt(0)}
              </div>
            )}
            <div>
              <h2 className="text-base font-bold text-white leading-tight">{account.label}</h2>
              <p className="text-xs text-gray-400">Quick Config & Inspection</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-white/5 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Drawer Body */}
        <div className="p-6 space-y-6 flex-1">
          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 gap-3 p-4 bg-[#181920] rounded-2xl border border-white/5">
            <div>
              <span className="text-[11px] text-gray-400 uppercase font-medium">Saldo Gems</span>
              <div className="text-xl font-bold text-white mt-0.5">
                {account.metrics?.gems_balance.toLocaleString()} 💎
              </div>
            </div>
            <div>
              <span className="text-[11px] text-gray-400 uppercase font-medium">Stok Farmable</span>
              <div className="text-xl font-bold text-amber-400 mt-0.5">
                {account.metrics?.stock_remaining} pcs
              </div>
            </div>
          </div>

          {/* Configuration Form */}
          <form onSubmit={handleSave} className="space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-discord-blurple flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5" />
              Pengaturan Akun
            </h3>

            <div>
              <label className="text-xs font-semibold text-gray-300 block mb-1">
                Label / Nickname Akun
              </label>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                required
                className="w-full bg-[#181920] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-discord-blurple"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-300 block mb-1">
                Discord Channel / Thread ID
              </label>
              <input
                type="text"
                value={channelId}
                onChange={(e) => setChannelId(e.target.value)}
                required
                className="w-full bg-[#181920] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs font-mono text-white focus:outline-none focus:border-discord-blurple"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-gray-300 block mb-1">
                  Target Farmable
                </label>
                <select
                  value={farmableItem}
                  onChange={(e) => setFarmableItem(e.target.value)}
                  className="w-full bg-[#181920] border border-white/10 rounded-xl px-3 py-2.5 text-xs text-white focus:outline-none focus:border-discord-blurple capitalize"
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
                  Gem Floor (Min)
                </label>
                <input
                  type="number"
                  value={gemFloor}
                  onChange={(e) => setGemFloor(Number(e.target.value))}
                  min={0}
                  step={500}
                  className="w-full bg-[#181920] border border-white/10 rounded-xl px-3 py-2.5 text-xs font-mono text-white focus:outline-none focus:border-discord-blurple"
                />
              </div>
            </div>

            <div className="pt-2 flex items-center gap-2">
              <button
                type="submit"
                disabled={isSaving}
                className="flex-1 bg-gradient-to-r from-discord-blurple to-indigo-600 hover:from-discord-blurple/90 hover:to-indigo-500 text-white text-xs font-semibold py-2.5 rounded-xl shadow-lg shadow-discord-blurple/20 flex items-center justify-center gap-2 transition"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Simpan Perubahan</span>
              </button>

              <button
                type="button"
                onClick={handleDelete}
                className="p-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 transition"
                title="Hapus Akun"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </form>

          {/* Dedicated Full Page Link */}
          <div className="pt-2">
            <Link
              href={`/accounts/${account.id}`}
              className="w-full py-2.5 px-4 rounded-xl bg-[#1e2028] hover:bg-discord-blurple hover:text-white text-gray-300 border border-white/10 text-xs font-semibold flex items-center justify-center gap-2 transition"
            >
              <span>Buka Halaman Analisis Lengkap & Riwayat Grafik</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          </div>

          {/* Recent Event Logs */}
          <div className="space-y-3 pt-4 border-t border-white/5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-discord-blurple" />
              5 Aktivitas Terakhir
            </h3>

            {recentLogs.length === 0 ? (
              <p className="text-xs text-gray-500">Belum ada riwayat aktivitas yang tercatat.</p>
            ) : (
              <div className="space-y-2">
                {recentLogs.map((log) => (
                  <div
                    key={log.id}
                    className="p-3 rounded-xl bg-[#181920] border border-white/5 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between text-[10px] text-gray-400 font-mono">
                      <span className="font-semibold text-discord-blurple">{log.event_type}</span>
                      <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <p className="text-gray-300 text-[11px] leading-relaxed">{log.message}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
