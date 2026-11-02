import { createClient } from "tinacms/dist/client";
import { queries } from "./types";
export const client = createClient({ url: 'http://localhost:4001/graphql', token: '4368a4434a8fe21b3982dca698ce282721257011', queries,  });
export default client;
  