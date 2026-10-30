import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { AUTH_COOKIE_NAME } from './lib/constants';

const SECRET_KEY = process.env.AUTH_SECRET || 'monitoring_master_secret_key_growcord_2026';

function bufferToHex(buffer: ArrayBuffer): string {
  const byteArray = new Uint8Array(buffer);
  return Array.from(byteArray)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

function base64urlDecode(str: string): string {
  // convert base64url to base64
  let b64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (b64.length % 4) {
    b64 += '=';
  }
  return atob(b64);
}

async function verifyEdgeToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  try {
    const parts = token.split('.');
    if (parts.length !== 2) return false;
    const [payloadB64, signatureHex] = parts;

    const json = base64urlDecode(payloadB64);
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      'raw',
      enc.encode(SECRET_KEY),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify']
    );

    // Convert hex signature back to bytes
    const match = signatureHex.match(/.{1,2}/g);
    if (!match) return false;
    const sigBytes = new Uint8Array(match.map((byte) => parseInt(byte, 16)));

    const isValid = await crypto.subtle.verify('HMAC', key, sigBytes, enc.encode(json));
    if (!isValid) return false;

    const payload = JSON.parse(json);
    if (!payload.auth || typeof payload.exp !== 'number' || payload.exp < Date.now()) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Paths that do not require authentication
  if (
    pathname.startsWith('/login') ||
    pathname.startsWith('/api/auth') ||
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon.ico') ||
    pathname.startsWith('/public')
  ) {
    return NextResponse.next();
  }

  const cookie = req.cookies.get(AUTH_COOKIE_NAME);
  const isAuthenticated = await verifyEdgeToken(cookie?.value);

  if (!isAuthenticated) {
    const loginUrl = new URL('/login', req.url);
    if (pathname !== '/') {
      loginUrl.searchParams.set('redirect', pathname);
    }
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
