import { NextRequest, NextResponse } from 'next/server';
import { supabase, isSupabaseConfigured } from '@/lib/supabase';
import { CommandType } from '@/lib/types';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { account_id, command, payload } = body;

    if (!account_id || !command) {
      return NextResponse.json({ error: 'account_id dan command wajib diisi' }, { status: 400 });
    }

    // If Supabase is connected, insert directly to bot_commands table
    if (isSupabaseConfigured && supabase) {
      const { data, error } = await supabase
        .from('bot_commands')
        .insert({
          account_id,
          command,
          payload: payload || {},
          status: 'PENDING',
        })
        .select()
        .single();

      if (error) {
        return NextResponse.json({ error: error.message }, { status: 500 });
      }

      return NextResponse.json({ success: true, command: data });
    }

    // Otherwise return success for simulated handling
    return NextResponse.json({
      success: true,
      message: 'Command diproses via Simulation Store',
      command: {
        account_id,
        command,
        payload,
        status: 'EXECUTED',
        created_at: new Date().toISOString(),
      },
    });
  } catch (error) {
    return NextResponse.json({ error: 'Gagal memproses command' }, { status: 500 });
  }
}
