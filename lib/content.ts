import fs from "fs";
import path from "path";

export type ArtItem = {
  slug: string;
  image: string;
  caption: string;
  alt_text: string;
  hashtags: string;
  posted: boolean;
};

function load(dir: string): ArtItem[] {
  try {
    if (!fs.existsSync(dir)) return [];
    const files = fs.readdirSync(dir).filter((f) => f.endsWith(".json"));
    return files
      .map((f) => {
        try {
          const filePath = path.join(dir, f);
          const content = fs.readFileSync(filePath, "utf8");
          const data = JSON.parse(content);
          
          let image = data.image || "";
          if (image && !image.startsWith("/")) {
            image = image.startsWith("art/") ? `/${image}` : `/art/${image}`;
          }

          return {
            slug: f.replace(".json", ""),
            image,
            caption: data.caption || "",
            alt_text: data.alt_text || "",
            hashtags: data.hashtags || "",
            posted: data.posted || false,
          };
        } catch (e) {
          console.error(`Error parsing ${f}:`, e);
          return null;
        }
      })
      .filter((item): item is ArtItem => item !== null)
      .sort((a, b) => b.slug.localeCompare(a.slug));
  } catch (e) {
    return [];
  }
}

export function getArtworks(): ArtItem[] {
  return load(path.join(process.cwd(), "content/artworks"));
}

export function getSketches(): ArtItem[] {
  return load(path.join(process.cwd(), "content/sketches"));
}
