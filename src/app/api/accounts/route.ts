import { NextRequest, NextResponse } from 'next/server';
import { supabase, isSupabaseConfigured } from '@/lib/supabase';
import { encryptToken } from '@/lib/crypto';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { label, token, channel_id, farmable_item, gem_floor, avatar_url } = body;

    if (!label || !token || !channel_id) {
      return NextResponse.json({ error: 'Label, token, dan channel_id wajib diisi' }, { status: 400 });
    }

    // Encrypt token using AES-256-GCM
    const encryptedToken = encryptToken(token);

    if (isSupabaseConfigured && supabase) {
      const { data, error } = await supabase
        .from('accounts')
        .insert({
          label: label.trim(),
          encrypted_token: encryptedToken,
          channel_id: channel_id.trim(),
          farmable_item: farmable_item || "Pot O' Gems",
          gem_floor: Number(gem_floor) || 2000,
          avatar_url: avatar_url || null,
          status: 'ACTIVE',
        })
        .select()
        .single();

      if (error) {
        return NextResponse.json({ error: error.message }, { status: 500 });
      }

      return NextResponse.json({ success: true, account: data });
    }

    return NextResponse.json({
      success: true,
      account: {
        id: 'acc-' + Math.random().toString(36).substring(2, 9),
        label: label.trim(),
        encrypted_token: encryptedToken,
        channel_id: channel_id.trim(),
        farmable_item: farmable_item || "Pot O' Gems",
        gem_floor: Number(gem_floor) || 2000,
        status: 'ACTIVE',
        created_at: new Date().toISOString(),
      },
    });
  } catch (error) {
    return NextResponse.json({ error: 'Gagal memproses pendaftaran akun' }, { status: 500 });
  }
}
