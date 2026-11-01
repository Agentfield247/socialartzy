import { defineConfig } from "tinacms";

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
        fields: {
          image: { type: "image", label: "Image", required: true },
          caption: { type: "string", label: "Caption", widget: "textarea" },
          alt_text: {
            type: "string",
            label: "Alt Text (required for accessibility)",
            required: true,
            widget: "textarea",
          },
          hashtags: { type: "string", label: "Hashtags", widget: "textarea" },
          post_to_instagram: {
            type: "boolean",
            label: "Post to Instagram?",
            description: "Uncheck for sketches you don't want on Instagram",
            default: true,
          },
          pinterest_board: { type: "string", label: "Pinterest Board Name" },
          posted: { type: "boolean", label: "Posted?", readOnly: true },
          posted_at: { type: "string", label: "Posted At", readOnly: true },
        },
      },
      {
        name: "artwork",
        label: "Complete Artworks",
        path: "content/artworks",
        format: "json",
        ui: { allowedActions: { create: true, delete: true } },
        fields: {
          image: { type: "image", label: "Image", required: true },
          caption: { type: "string", label: "Caption", widget: "textarea" },
          alt_text: {
            type: "string",
            label: "Alt Text (required for accessibility)",
            required: true,
            widget: "textarea",
          },
          hashtags: { type: "string", label: "Hashtags", widget: "textarea" },
          post_to_instagram: {
            type: "boolean",
            label: "Post to Instagram?",
            description: "Uncheck for sketches you don't want on Instagram",
            default: true,
          },
          pinterest_board: { type: "string", label: "Pinterest Board Name" },
          posted: { type: "boolean", label: "Posted?", readOnly: true },
          posted_at: { type: "string", label: "Posted At", readOnly: true },
        },
      },
    ],
  },
});