import { getSketches } from "@/lib/content";
import GalleryGrid from "@/components/GalleryGrid";

export default function SketchesPage() {
  const items = getSketches();
  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Sketches</h1>
      <GalleryGrid items={items} />
    </main>
  );
}
