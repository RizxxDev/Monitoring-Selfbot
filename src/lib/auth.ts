import { AUTH_COOKIE_NAME, DEFAULT_MASTER_PASSWORD } from './constants';

const SECRET_KEY = process.env.AUTH_SECRET || 'monitoring_master_secret_key_growcord_2026';

// Edge-compatible HMAC-SHA256 signature
async function getCryptoKey(): Promise<CryptoKey> {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    'raw',
    enc.encode(SECRET_KEY),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  );
}

function bufferToHex(buffer: ArrayBuffer): string {
  const byteArray = new Uint8Array(buffer);
  return Array.from(byteArray)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function createSessionToken(): Promise<string> {
  const payload = {
    auth: true,
    exp: Date.now() + 24 * 60 * 60 * 1000, // 24 hours
  };
  const json = JSON.stringify(payload);
  const enc = new TextEncoder();
  const key = await getCryptoKey();
  const signatureBuffer = await crypto.subtle.sign('HMAC', key, enc.encode(json));
  const signatureHex = bufferToHex(signatureBuffer);
  
  // Safe base64url encode
  const b64 = Buffer.from(json).toString('base64url');
  return `${b64}.${signatureHex}`;
}

export async function verifySessionToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  try {
    const parts = token.split('.');
    if (parts.length !== 2) return false;
    const [payloadB64, signatureHex] = parts;

    const json = Buffer.from(payloadB64, 'base64url').toString('utf8');
    const enc = new TextEncoder();
    const key = await getCryptoKey();
    const signatureBuffer = await crypto.subtle.sign('HMAC', key, enc.encode(json));
    const expectedHex = bufferToHex(signatureBuffer);

    if (signatureHex !== expectedHex) return false;

    const payload = JSON.parse(json);
    if (!payload.auth || typeof payload.exp !== 'number' || payload.exp < Date.now()) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

// In-memory rate limiting map: ip -> { attempts: number, lockUntil: number }
const rateLimitMap = new Map<string, { attempts: number; lockUntil: number }>();
const MAX_ATTEMPTS = 5;
const LOCKOUT_DURATION_MS = 3 * 60 * 1000; // 3 minutes

export function checkRateLimit(identifier: string): { isLocked: boolean; remainingAttempts: number; retryAfterSec?: number } {
  const now = Date.now();
  const record = rateLimitMap.get(identifier);

  if (!record) {
    return { isLocked: false, remainingAttempts: MAX_ATTEMPTS };
  }

  if (record.lockUntil > now) {
    const retryAfterSec = Math.ceil((record.lockUntil - now) / 1000);
    return { isLocked: true, remainingAttempts: 0, retryAfterSec };
  }

  if (record.lockUntil > 0 && record.lockUntil <= now) {
    rateLimitMap.delete(identifier);
    return { isLocked: false, remainingAttempts: MAX_ATTEMPTS };
  }

  const remaining = Math.max(0, MAX_ATTEMPTS - record.attempts);
  return { isLocked: false, remainingAttempts: remaining };
}

export function recordFailedAttempt(identifier: string): { isLocked: boolean; remainingAttempts: number; retryAfterSec?: number } {
  const now = Date.now();
  const record = rateLimitMap.get(identifier) || { attempts: 0, lockUntil: 0 };
  record.attempts += 1;

  if (record.attempts >= MAX_ATTEMPTS) {
    record.lockUntil = now + LOCKOUT_DURATION_MS;
    rateLimitMap.set(identifier, record);
    return { isLocked: true, remainingAttempts: 0, retryAfterSec: Math.ceil(LOCKOUT_DURATION_MS / 1000) };
  }

  rateLimitMap.set(identifier, record);
  return { isLocked: false, remainingAttempts: MAX_ATTEMPTS - record.attempts };
}

export function resetRateLimit(identifier: string) {
  rateLimitMap.delete(identifier);
}

export function verifyMasterPassword(password: string): boolean {
  const configuredPassword = process.env.MASTER_PASSWORD || DEFAULT_MASTER_PASSWORD;
  return password === configuredPassword;
}
