import { NextResponse } from 'next/server';
import { AUTH_COOKIE_NAME } from '@/lib/constants';

export async function POST() {
  const response = NextResponse.json({ success: true, message: 'Berhasil logout' });
  response.cookies.set({
    name: AUTH_COOKIE_NAME,
    value: '',
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  });
  return response;
}
