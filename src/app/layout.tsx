import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Growcord Farm Monitor | Multi-Account Dashboard',
  description: 'Real-time multi-account monitoring, remote control, and analytics for Discord Growcord farm bots.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id" className="dark">
      <body className="bg-[#0e0f14] text-[#e0e2e8] min-h-screen antialiased selection:bg-[#5865F2] selection:text-white">
        {children}
      </body>
    </html>
  );
}
