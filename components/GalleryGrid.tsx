"use client";

import { useState } from "react";
import Image from "next/image";
import Lightbox from "./Lightbox";
import { ArtItem } from "@/lib/content";

export default function GalleryGrid({ items }: { items: ArtItem[] }) {
  const [selected, setSelected] = useState<ArtItem | null>(null);

  if (!items || items.length === 0) {
    return (
      <div className="text-center py-20 text-gray-500">
        No art yet — upload from /admin
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {items.map((item, index) => (
          <button
            key={index}
            onClick={() => setSelected(item)}
            className="relative aspect-[4/5] w-full overflow-hidden rounded-lg shadow-md hover:opacity-90 transition-opacity"
          >
            <Image
              src={item.image}
              alt={item.alt_text}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              quality={80}
              className="object-cover"
            />
          </button>
        ))}
      </div>
      <Lightbox item={selected} onClose={() => setSelected(null)} />
    </>
  );
}
