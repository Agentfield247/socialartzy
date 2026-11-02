import { getArtworks } from "@/lib/content";
import GalleryGrid from "@/components/GalleryGrid";

export default function Home() {
  const items = getArtworks();
  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Complete Artworks</h1>
      <GalleryGrid items={items} />
    </main>
  );
}
