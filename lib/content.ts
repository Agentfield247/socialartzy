import fs from 'fs';
import path from 'path';

const ARTWORKS_DIR = path.join(process.cwd(), 'content', 'artworks');
const SKETCHES_DIR = path.join(process.cwd(), 'content', 'sketches');

export type ArtItem = {
  slug: string;
  image: string;
  caption: string;
  alt_text: string;
  hashtags: string;
  posted: boolean;
};

function load(dir) {
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'));
  return files
    .map(f => {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
        let img = data.image;
        if (img.startsWith('/')) ;
        else if (img.startsWith('art/')) img = '/' + img;
        else img = '/' + img;
        return {
          slug: f.replace('.json', ''),
          image: img,
          caption: data.caption,
          alt_text: data.alt_text,
          hashtags: data.hashtags,
          posted: data.posted,
        };
      } catch { return null; }
    })
    .filter(x => x != null)
    .sort((a, b) => (b.posted ? -1 : 1) - (a.posted ? -1 : 1));
}

export function getArtworks() { return load(path.join(process.cwd(), 'content/artworks')); }

export function getSketches() { return load(path.join(process.cwd(), 'content/sketches')); }
