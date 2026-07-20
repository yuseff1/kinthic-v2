import type { Metadata } from 'next';
import { Poppins, Lora, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const poppins = Poppins({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-display',
});

const lora = Lora({
  subsets: ['latin'],
  weight: ['400'],
  variable: '--font-serif',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-mono',
});

export const metadata: Metadata = {
  title: 'Kinthic Studio',
  description: 'Epistemic Graph and Control Center for Kinthic AGI',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${poppins.variable} ${lora.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-canvas text-text-primary font-display overflow-hidden h-screen w-screen selection:bg-terracotta/30">
        {children}
      </body>
    </html>
  );
}
