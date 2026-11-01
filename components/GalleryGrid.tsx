"use client";

interface ArtItem {
  slug: string;
  image: string;
  caption: string;
  alt_text: string;
  hashtags: string;
}

export function GalleryGrid({ items }: { items: ArtItem[] }) {
  if (items.length === 0) {
    return <div className="center-text py-12">No art yet - upload from /admin</div>;
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {items.map((item) => (
        <button key={item.slug} className="relative aspect-[4/5] overflow-hidden rounded-lg hover:opacity-90 transition-opacity">
          <Image
            src={item.image}
            alt={item.alt_text}
            sizes="(max-width:640px) 100vw, (max-width:1024px) 50vw, 33vw"
            quality={80}
            className="object-cover rounded-lg w-full h-full"
          />
        </button>
      ))}
    </div>
  );
}