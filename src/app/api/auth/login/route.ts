import { NextRequest, NextResponse } from 'next/server';
import { AUTH_COOKIE_NAME } from '@/lib/constants';
import { checkRateLimit, recordFailedAttempt, resetRateLimit, verifyMasterPassword, createSessionToken } from '@/lib/auth';

export async function POST(req: NextRequest) {
  try {
    const ip = req.headers.get('x-forwarded-for')?.split(',')[0] || '127.0.0.1';
    
    // Check rate limit
    const limitStatus = checkRateLimit(ip);
    if (limitStatus.isLocked) {
      return NextResponse.json(
        {
          error: `Terlalu banyak percobaan gagal. Akses dikunci sementara selama ${limitStatus.retryAfterSec} detik.`,
          isLocked: true,
          retryAfterSec: limitStatus.retryAfterSec,
        },
        { status: 429 }
      );
    }

    const body = await req.json();
    const { password } = body;

    if (!password) {
      return NextResponse.json({ error: 'Password wajib diisi' }, { status: 400 });
    }

    const isValid = verifyMasterPassword(password);
    if (!isValid) {
      const failedStatus = recordFailedAttempt(ip);
      if (failedStatus.isLocked) {
        return NextResponse.json(
          {
            error: `Password salah! Akses dikunci sementara selama ${failedStatus.retryAfterSec} detik karena mencapai 5 kali kegagalan.`,
            isLocked: true,
            remainingAttempts: 0,
            retryAfterSec: failedStatus.retryAfterSec,
          },
          { status: 429 }
        );
      }

      return NextResponse.json(
        {
          error: `Password salah! Sisa percobaan: ${failedStatus.remainingAttempts}`,
          remainingAttempts: failedStatus.remainingAttempts,
          isLocked: false,
        },
        { status: 401 }
      );
    }

    // Success: reset rate limit and issue cookie
    resetRateLimit(ip);
    const sessionToken = await createSessionToken();

    const response = NextResponse.json({
      success: true,
      message: 'Autentikasi berhasil',
    });

    response.cookies.set({
      name: AUTH_COOKIE_NAME,
      value: sessionToken,
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      path: '/',
      maxAge: 24 * 60 * 60, // 24 hours
    });

    return response;
  } catch (error) {
    return NextResponse.json({ error: 'Terjadi kesalahan internal server' }, { status: 500 });
  }
}
