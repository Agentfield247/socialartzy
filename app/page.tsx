import Image from 'next/image';
import GalleryGrid from '@/components/GalleryGrid';

export default function Home() {
  return (
    <main className='max-w-6xl mx-auto px-4 py-8'>
      <h1 className='text-3xl font-bold mb-6'>Complete Artworks</h1>
      <GalleryGrid />
    </main>
  );
}
