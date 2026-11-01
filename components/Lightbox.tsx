"use client";

interface ArtItem {
  slug: string;
  image: string;
  caption: string;
  alt_text: string;
}

export function Lightbox({ item, onClose }: { item: ArtItem | null; onClose: () => void }) {
  if (!item) return null;
  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
      aria-label="Lightbox"
      role="dialog"
      aria-modal="true"
    >
      <div className="relative max-w-3xl max-h-[90vh] w-full">
        <Image
          src={item.image}
          alt={item.alt_text}
          width={1200}
          height={1500}
          className="object-contain w-full h-auto max-h-[75vh]"
        />
        <div className="absolute top-4 left-4 text-white">
          {item.caption}
        </div>
        <div className="absolute bottom-4 right-4 text-white">
          {item.alt_text}
        </div>
        <button
          onClick={onClose}
          className="absolute top-6 right-6 text-2xl text-white"
          aria-label="Close"
        >&times;</button>
      </div>
    </div>
  );
}