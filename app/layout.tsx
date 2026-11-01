import './globals.css';

export const metadata = {
  title: 'SocialArtzy',
  description: 'Art portfolio',
};

export default function RootLayout({
  children,
}) {
  return (
    <html lang='en'>
      <body>
        <nav className='mb-8'>
          <a href='/' className='mr-4'>Complete Artworks</a>
          <a href='/sketches' className=''>Sketches</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
