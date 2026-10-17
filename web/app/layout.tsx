import type { Metadata } from 'next';
import './globals.css';
import './motion.css';

export const metadata: Metadata = { title: 'PharmaOne AI', description: 'From Government Alerts to Pharmacy Action' };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }
