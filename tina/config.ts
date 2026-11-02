import { defineConfig, TinaField } from "tinacms";

const itemFields: TinaField[] = [
  { type: "image", name: "image", label: "Image", required: true },
  { type: "string", name: "caption", label: "Caption", ui: { component: "textarea" } },
  { type: "string", name: "alt_text", label: "Alt Text (required for accessibility)", required: true, ui: { component: "textarea" } },
  { type: "string", name: "hashtags", label: "Hashtags", ui: { component: "textarea" } },
  { type: "boolean", name: "post_to_instagram", label: "Post to Instagram?", description: "Uncheck for sketches you don't want on Instagram" },
  { type: "string", name: "pinterest_board", label: "Pinterest Board Name" },
  { type: "boolean", name: "posted", label: "Posted?" },
  { type: "string", name: "posted_at", label: "Posted At" },
];

export default defineConfig({
  branch: process.env.GITHUB_BRANCH || process.env.VERCEL_GIT_COMMIT_REF || "main",
  clientId: process.env.NEXT_PUBLIC_TINA_CLIENT_ID,
  token: process.env.TINA_TOKEN,
  build: { outputFolder: "admin", publicFolder: "public" },
  media: { tina: { mediaRoot: "art", publicFolder: "public" } },
  schema: {
    collections: [
      {
        name: "sketch",
        label: "Sketches",
        path: "content/sketches",
        format: "json",
        ui: { allowedActions: { create: true, delete: true } },
        fields: itemFields,
      },
      {
        name: "artwork",
        label: "Complete Artworks",
        path: "content/artworks",
        format: "json",
        ui: { allowedActions: { create: true, delete: true } },
        fields: itemFields,
      },
    ],
  },
});