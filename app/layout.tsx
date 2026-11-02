import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SocialArtzy",
  description: "Art portfolio",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <header className="bg-white shadow-sm">
          <nav className="max-w-6xl mx-auto px-4 py-4 flex gap-6">
            <Link href="/" className="font-semibold hover:text-blue-600 transition-colors">
              Complete Artworks
            </Link>
            <Link href="/sketches" className="font-semibold hover:text-blue-600 transition-colors">
              Sketches
            </Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
