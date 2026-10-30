import crypto from 'crypto';

const DEFAULT_SECRET = process.env.ENCRYPTION_KEY || 'growcord_super_secret_aes_key_2026';

export function deriveKey(secret: string = DEFAULT_SECRET): Buffer {
  return crypto.createHash('sha256').update(secret).digest();
}

export function encryptToken(plainToken: string, secret: string = DEFAULT_SECRET): string {
  if (!plainToken) return '';
  const key = deriveKey(secret);
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const encrypted = Buffer.concat([cipher.update(plainToken, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  const combined = Buffer.concat([iv, encrypted, tag]);
  return 'aes:' + combined.toString('base64');
}

export function decryptToken(encryptedStr: string, secret: string = DEFAULT_SECRET): string {
  if (!encryptedStr || !encryptedStr.startsWith('aes:')) return encryptedStr;
  try {
    const key = deriveKey(secret);
    const combined = Buffer.from(encryptedStr.slice(4), 'base64');
    const iv = combined.subarray(0, 12);
    const tag = combined.subarray(combined.length - 16);
    const ciphertext = combined.subarray(12, combined.length - 16);
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
    decipher.setAuthTag(tag);
    return decipher.update(ciphertext, undefined, 'utf8') + decipher.final('utf8');
  } catch (err) {
    console.error('Failed to decrypt token:', err);
    return encryptedStr;
  }
}
