"use client";

import Image from "next/image";
import { useEffect } from "react";
import { ArtItem } from "@/lib/content";

export default function Lightbox({
  item,
  onClose,
}: {
  item: ArtItem | null;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  if (!item) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-3xl max-h-[90vh] w-full flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-white text-3xl hover:text-gray-300"
        >
          &times;
        </button>
        <div className="relative w-full h-[75vh]">
          <Image
            src={item.image}
            alt={item.alt_text}
            fill
            className="object-contain"
            sizes="(max-width: 1200px) 100vw, 1200px"
          />
        </div>
        <div className="mt-4 text-center text-white">
          <p className="text-lg">{item.caption}</p>
          <p className="text-sm text-gray-400 mt-2">{item.alt_text}</p>
        </div>
      </div>
    </div>
  );
}
