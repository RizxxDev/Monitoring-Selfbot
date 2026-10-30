'use client';

import React, { useState } from 'react';
import { X, Key, Hash, Shield, Plus, Check } from 'lucide-react';
import { FARMABLE_ITEMS } from '@/lib/constants';
import { simulationStore } from '@/lib/simulation-store';
import { useToast } from './Toast';

interface AddAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AddAccountModal({ isOpen, onClose }: AddAccountModalProps) {
  const { showToast } = useToast();

  const [label, setLabel] = useState('');
  const [token, setToken] = useState('');
  const [channelId, setChannelId] = useState('');
  const [farmableItem, setFarmableItem] = useState(FARMABLE_ITEMS[0]);
  const [gemFloor, setGemFloor] = useState<number>(2000);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!label.trim() || !token.trim() || !channelId.trim()) return;

    setLoading(true);

    // Mask / simulate token encryption
    const encryptedToken = `enc_aes256_${btoa(token.slice(0, 15))}...`;

    simulationStore.addAccount({
      label: label.trim(),
      encrypted_token: encryptedToken,
      channel_id: channelId.trim(),
      farmable_item: farmableItem,
      gem_floor: Number(gemFloor),
      status: 'ACTIVE',
      avatar_url: `https://images.unsplash.com/photo-${1600000000000 + Math.floor(Math.random() * 90000000)}?w=128&q=80`,
    });

    setLoading(false);
    showToast({
      type: 'success',
      title: 'Akun Ditambahkan',
      message: `Akun bot '${label}' siap digunakan dan aktif memantau channel ${channelId}.`,
    });

    // Reset & close
    setLabel('');
    setToken('');
    setChannelId('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/70 backdrop-blur-sm transition-opacity animate-fadeIn"
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-lg bg-[#14151b] border border-white/10 rounded-2xl shadow-2xl p-6 sm:p-7 z-10 animate-fadeIn">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/10 mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-discord-blurple/20 text-discord-blurple border border-discord-blurple/30 flex items-center justify-center">
              <Plus className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Tambah Akun Bot Baru</h2>
              <p className="text-xs text-gray-400">Registrasi akun farm Growcord ke sistem monitoring</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-white/5 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-gray-300 block mb-1.5">
              Label / Nama Akun
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Contoh: Farmer-Alpha-05"
              required
              className="w-full bg-[#181920] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs sm:text-sm text-white placeholder-gray-500 focus:outline-none focus:border-discord-blurple transition"
            />
          </div>

          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-discord-blurple" />
                Discord User Token
              </label>
              <span className="text-[10px] text-emerald-400 font-medium">Otomatis Terenkripsi AES-256</span>
            </div>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="MTAyNDk2... (User token akun Discord)"
              required
              className="w-full bg-[#181920] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs sm:text-sm text-white placeholder-gray-500 font-mono focus:outline-none focus:border-discord-blurple transition"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-300 flex items-center gap-1.5 mb-1.5">
              <Hash className="w-3.5 h-3.5 text-discord-blurple" />
              Growcord Farm Channel / Thread ID
            </label>
            <input
              type="text"
              value={channelId}
              onChange={(e) => setChannelId(e.target.value)}
              placeholder="Contoh: 119283748291028374"
              required
              className="w-full bg-[#181920] border border-white/10 rounded-xl px-3.5 py-2.5 text-xs sm:text-sm text-white placeholder-gray-500 font-mono focus:outline-none focus:border-discord-blurple transition"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-gray-300 block mb-1.5">
                Target Farmable Item
              </label>
              <select
                value={farmableItem}
                onChange={(e) => setFarmableItem(e.target.value)}
                className="w-full bg-[#181920] border border-white/10 rounded-xl px-3 py-2.5 text-xs sm:text-sm text-white focus:outline-none focus:border-discord-blurple capitalize"
              >
                {FARMABLE_ITEMS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-gray-300 block mb-1.5">
                Gem Floor Minimal
              </label>
              <input
                type="number"
                value={gemFloor}
                onChange={(e) => setGemFloor(Number(e.target.value))}
                min={0}
                step={500}
                className="w-full bg-[#181920] border border-white/10 rounded-xl px-3 py-2.5 text-xs sm:text-sm font-mono text-white focus:outline-none focus:border-discord-blurple"
              />
            </div>
          </div>

          {/* Action Footer */}
          <div className="pt-4 flex items-center justify-end gap-3 border-t border-white/5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/5 transition"
            >
              Batal
            </button>

            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-discord-blurple to-indigo-600 hover:from-discord-blurple/90 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-discord-blurple/20 flex items-center gap-2 transition"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  <span>Simpan & Aktifkan</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
