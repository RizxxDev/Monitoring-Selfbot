import { NextRequest, NextResponse } from 'next/server';
import { AUTH_COOKIE_NAME } from '@/lib/constants';
import { verifySessionToken } from '@/lib/auth';

export async function GET(req: NextRequest) {
  const cookie = req.cookies.get(AUTH_COOKIE_NAME);
  const isAuthenticated = await verifySessionToken(cookie?.value);

  return NextResponse.json({
    authenticated: isAuthenticated,
  });
}
